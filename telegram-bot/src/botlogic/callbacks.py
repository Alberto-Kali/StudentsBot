import re
from typing import Union, Optional
import uuid
import base64
from io import BytesIO

from aiogram import types, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    Message,
    CallbackQuery,
    BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.deep_linking import create_start_link

from botlogic.bot import bot, dp, router, db
from botlogic.menu import main_menu

import asyncio


class Form(StatesGroup):
    WAITING_FOR_PHOTO = State()   # ждём фото для анкеты
    WAITING_FOR_BIO = State()     # ждём новый текст био
    RATING = State()              # режим бесконечной оценки анкет
    WAITING_FOR_TAG_NAME = State() # ждём текст нового тега
    WAITING_FOR_DM = State()         # ждём текст личного сообщения


async def cbmd(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    return 0


# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======

def backbutton(user=None) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back"
        )
    )
    return builder.as_markup()


def closebutton() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Закрыть ✅",
            callback_data="close"
        )
    )
    return builder.as_markup()


def repeatbutton(user=None) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="♻️ Повторить текущие",
            callback_data="clear_reviews"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back"
        )
    )
    return builder.as_markup()


def build_my_profile_keyboard(user) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Изменить
    builder.row(
        InlineKeyboardButton(
            text="✏️ Изменить анкету",
            callback_data="edit_profile"
        )
    )

    # Скрыть / Опубликовать
    if user.published:
        builder.row(
            InlineKeyboardButton(
                text="🙈 Скрыть анкету",
                callback_data="hide_profile"
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="📢 Опубликовать анкету",
                callback_data="publish_profile"
            )
        )

    # Назад
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back"
        )
    )

    return builder.as_markup()


def build_edit_profile_menu(user, has_tg_username: bool) -> types.InlineKeyboardMarkup:
    """
    Меню редактирования анкеты:
    - Изменить био
    - Фото (подменю)
    - Показ/скрытие username (если есть username в Telegram)
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="✏️ Изменить био",
            callback_data="edit_bio"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🖼 Фото",
            callback_data="edit_photo"
        )
    )

    if has_tg_username or user.telegram_uname:
        # Если в анкете username есть — предлагаем скрыть
        if user.username_hidden:
            text = "👁 Отображать username"
        else:
            text = "🙈 Не отображать username"

        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data="toggle_uname"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back"
        )
    )

    return builder.as_markup()


def build_rating_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏷 Тэгнуть", callback_data="rate_tag"),
        InlineKeyboardButton(text="💌 Написать", callback_data="write_user")
    )
    builder.row(
        InlineKeyboardButton(text="👍 Лайк", callback_data="rate_like"),
        InlineKeyboardButton(text="👎 Дизлайк", callback_data="rate_dislike"),
    )
    builder.row(
        InlineKeyboardButton(text="⏭ Скип", callback_data="rate_skip"),
        InlineKeyboardButton(text="🏁 Закончить оценку", callback_data="rate_finish"),
    )
    return builder.as_markup()


def build_tags_keyboard(target_telegram_id: int) -> types.InlineKeyboardMarkup:
    """
    Клавиатура для выбора тега. В callback_data кодируем id тега и телеграм id цели.
    Формат: 'tag_apply:{target_telegram_id}:{tag_id}'
    """
    tags = db.get_all_tags()
    builder = InlineKeyboardBuilder()
    for tag in tags:
        builder.row(
            InlineKeyboardButton(
                text=tag.name,
                callback_data=f"tag_apply:{target_telegram_id}:{tag.id}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад к оценке", callback_data="back_to_rating")
    )
    return builder.as_markup()


def build_profile_caption(user, is_owner: bool = False) -> str:
    bio = user.biography or "не указана"
    tags = db.get_tags_for_user(user.id)
    tags_str = ", ".join([t.name for t in tags]) if tags else "нет тегов"

    status = "✅ Анкета опубликована" if user.published else "❌ Анкета скрыта"

    if is_owner:
        caption = (
            f"🧑‍💻 <b>Ваша анкета</b>\n\n"
            f"👤 Имя: <b>{user.name}</b>\n"
            f"📎 Username: @{user.telegram_uname if user.telegram_uname else 'не указан'} | {"СК" if user.username_hidden else "ОТК"}\n\n" 
            f"📝 О себе: {bio}\n"
            f"🏷 Теги: {tags_str}\n\n"
            f"👍 Лайков: {user.liked} | 👎 Дизлайков: {user.disliked} | ⏭ Скипов: {user.skips}\n"
            f"{status}"
        )
    else:
        if user.username_hidden:
            usernamed = "скрыт"
        else:
            usernamed = f"@{user.telegram_uname if user.telegram_uname else 'не указан'}"
        caption = (
            f"👤 <b>{user.name}</b>\n"
            f"📝 О себе: {bio}\n"
            f"📎 Username: {usernamed}\n\n"
            f"🏷 Теги: {tags_str}\n\n"
            f"👍 {user.liked} | 👎 {user.disliked} | ⏭ {user.skips}"
        )
    return caption


async def send_user_profile_with_photo(
    chat_id: int,
    user,
    is_owner: bool = False,
    keyboard: Optional[types.InlineKeyboardMarkup] = None,
):
    photos = db.get_photos_for_user(user.id)
    caption = build_profile_caption(user, is_owner=is_owner)

    if photos:
        # Берем последнее фото
        last_photo = sorted(photos, key=lambda p: p.created_at)[-1]
        try:
            raw_bytes = base64.b64decode(last_photo.raw_png.encode("utf-8"))
            photo_file = BufferedInputFile(raw_bytes, filename="avatar.png")
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"Ошибка декодирования фото: {e}")
            # Если вдруг что-то не так с фото
            await bot.send_message(
                chat_id,
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
    else:
        # Фото нет — просто текст
        await bot.send_message(
            chat_id,
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def get_next_profile_for_rating(current_user):
    """
    Обёртка над функцией из БД.
    Должна вернуть другого опубликованного пользователя или None.
    """
    return db.get_random_published_user(exclude_telegram_id=current_user.telegram_id)


# ====== ОСНОВНОЙ CALLBACK-HANDLER ======

async def handle_button_press(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data
    user = db.get_user(callback.from_user.id)

    if not user:
        await callback.message.answer("Вы не зарегистрированы. Введите команду /start.")
        return

    if user.banned:
        await callback.message.answer("Вы забанены. Обратитесь к администратору.")
        return

    # ------ МОЯ АНКЕТА ------
    if action == "my_profile":
        await cbmd(callback)

        # Проверяем, есть ли фото — если нет, просим прислать
        photos = db.get_photos_for_user(user.id)
        if not photos:
            await callback.message.answer(
                "🖼 Для начала прикрепите фото для анкеты.\n\n"
                "Отправьте одно фото (ваш аватар)."
            )
            await state.set_state(Form.WAITING_FOR_PHOTO)
            return

        # Показываем анкету с фото
        keyboard = build_my_profile_keyboard(user)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=user,
            is_owner=True,
            keyboard=keyboard,
        )

    # ------ ИЗМЕНИТЬ АНКЕТУ (био) ------
    elif action == "edit_profile":
        await cbmd(callback)
        tg_uname = callback.from_user.username
        kb = build_edit_profile_menu(user, has_tg_username=bool(tg_uname))
        await callback.message.answer(
            "Что хотите изменить в анкете?",
            reply_markup=kb
        )

    # ------ ПЕРЕКЛЮЧЕНИЕ ОТОБРАЖЕНИЯ USERNAME ------
    elif action == "toggle_uname":
        await cbmd(callback)
        tg_uname = callback.from_user.username

        # Если сейчас username в анкете есть — скрываем
        if not user.username_hidden:
            db.edit_user(callback.from_user.id, username_hidden = 1)
            text = "Ваш username больше не отображается в анкете."
        else:
            if not tg_uname:
                kb = backbutton(user)
                await callback.message.answer(
                    "У вас нет username в Telegram — отображать нечего.",
                    reply_markup=kb
                )
                return
            db.edit_user(callback.from_user.id, username_hidden = 0)
            text = "Ваш username теперь отображается в анкете."

        kb = backbutton(user)
        await callback.message.answer(text, reply_markup=kb)

    # ------ ПОДМЕНЮ РАБОТЫ С ФОТО ------
    elif action == "edit_photo":
        await cbmd(callback)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🖼 Изменить фото",
                callback_data="photo_change"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить фото",
                callback_data="photo_add"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⏭ Пропустить",
                callback_data="photo_skip"
            )
        )
        await callback.message.answer(
            "Что хотите сделать с фото анкеты?",
            reply_markup=builder.as_markup()
        )

    elif action == "photo_change":
        await cbmd(callback)
        await state.update_data(photo_mode="change")
        await callback.message.answer("Отправьте новое фото для анкеты.")
        await state.set_state(Form.WAITING_FOR_PHOTO)

    #elif action == "photo_add":
    #    await cbmd(callback)
    #    await state.update_data(photo_mode="add")
    #    await callback.message.answer("Отправьте дополнительное фото для анкеты.")
    #    await state.set_state(Form.WAITING_FOR_PHOTO)

    elif action == "photo_skip":
        await cbmd(callback)
        # Просто снова показываем анкету
        keyboard = build_my_profile_keyboard(user)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=user,
            is_owner=True,
            keyboard=keyboard,
        )

    # ------ ИЗМЕНИТЬ АНКЕТУ (био) ------
    elif action == "edit_bio":
        await cbmd(callback)
        current_bio = user.biography or "не указана"
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="Оставить как есть",
                callback_data="bio_keep"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back"
            )
        )
        await callback.message.answer(
            f"Сейчас в анкете:\n\n{current_bio}\n\n"
            "Отправьте новый текст для раздела «О себе» или нажмите «Оставить как есть».",
            reply_markup=builder.as_markup()
        )
        await state.set_state(Form.WAITING_FOR_BIO)

    # ------ ОСТАВИТЬ БИО БЕЗ ИЗМЕНЕНИЙ ------
    elif action == "bio_keep":
        await cbmd(callback)
        await state.clear()
        user = db.get_user(callback.from_user.id)
        keyboard = build_my_profile_keyboard(user)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=user,
            is_owner=True,
            keyboard=keyboard,
        )

    # ------ СКРЫТЬ АНКЕТУ ------
    elif action == "hide_profile":
        await cbmd(callback)
        db.edit_user(callback.from_user.id, published=0)
        await callback.message.answer("🙈 Ваша анкета скрыта от других пользователей.")
        await main_menu(callback.message, callback.from_user.id)

    # ------ ОПУБЛИКОВАТЬ АНКЕТУ ------
    elif action == "publish_profile":
        await cbmd(callback)
        db.edit_user(callback.from_user.id, published=1)
        await callback.message.answer("📢 Ваша анкета теперь видна другим пользователям.")
        await main_menu(callback.message, callback.from_user.id)

    # ------ НАЧАТЬ ОЦЕНКУ ------
    elif action == "start_rating":
        await cbmd(callback)

        # Входим в режим оценки
        await state.set_state(Form.RATING)

        target = await get_next_profile_for_rating(user)
        if target == 0:
            keyboard = repeatbutton(user)
            await callback.message.answer(
                "Пока нет доступных анкет для оценки 😔",
                reply_markup=keyboard
            )
            await state.clear()
            return

        # сохраняем текущую цель в FSM
        await state.update_data(current_target_telegram_id=target.telegram_id)

        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=target,
            is_owner=False,
            keyboard=build_rating_keyboard(),
        )

    # ------ ЛАЙК ------
    elif action == "rate_like":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if not target_tg_id:
            await callback.answer("Ошибка: нет текущей анкеты.", show_alert=True)
            return

        target, is_new, changed = db.rate_user(
            rater_tg=callback.from_user.id,
            target_tg=target_tg_id,
            value=1
        )

        if not target:
            await callback.answer("Анкета не найдена.", show_alert=True)
            return

        # Уведомление оцениваемому (с кнопкой "Закрыть")
        try:
            if is_new:
                text = f"⭐️ Вас оценили: @{callback.from_user.username} поставил(а) вам 👍"
            elif changed:
                text = f"♻️ @{callback.from_user.username} изменил(а) свою оценку на 👍"
            else:
                text = None

            if text:
                kb = closebutton()
                await bot.send_message(
                    chat_id=target_tg_id,
                    text=text,
                    reply_markup=kb
                )
        except Exception as e:
            print(f"Ошибка отправки уведомления о лайке: {e}")

        # Следующая анкета
        db.add_review(callback.from_user.id, target_tg_id)
        next_target = await get_next_profile_for_rating(user)
        if next_target == 0:
            await cbmd(callback)
            kb = repeatbutton(user)
            await callback.message.answer(
                "Анкет больше нет. Вы молодец! 🎉",
                reply_markup=kb
            )
            await state.clear()
            return

        await state.update_data(current_target_telegram_id=next_target.telegram_id)
        await cbmd(callback)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=next_target,
            is_owner=False,
            keyboard=build_rating_keyboard(),
        )

    # ------ ДИЗЛАЙК ------
    elif action == "rate_dislike":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if not target_tg_id:
            await callback.answer("Ошибка: нет текущей анкеты.", show_alert=True)
            return

        target, is_new, changed = db.rate_user(
            rater_tg=callback.from_user.id,
            target_tg=target_tg_id,
            value=-1
        )

        if not target:
            await callback.answer("Анкета не найдена.", show_alert=True)
            return

        # Уведомление оцениваемому (с кнопкой "Закрыть")
        try:
            if is_new:
                text = f"⭐️ Вас оценили: @{callback.from_user.username} поставил(а) вам 👎"
            elif changed:
                text = f"♻️ @{callback.from_user.username} изменил(а) свою оценку на 👎"
            else:
                text = None

            if text:
                kb = closebutton()
                await bot.send_message(
                    chat_id=target_tg_id,
                    text=text,
                    reply_markup=kb
                )
        except Exception as e:
            print(f"Ошибка отправки уведомления о дизлайке: {e}")

        # Следующая анкета
        db.add_review(callback.from_user.id, target_tg_id)
        next_target = await get_next_profile_for_rating(user)
        if next_target == 0:
            await cbmd(callback)
            kb = repeatbutton(user)
            await callback.message.answer(
                "Анкет больше нет. Вы молодец! 🎉",
                reply_markup=kb
            )
            await state.clear()
            return

        await state.update_data(current_target_telegram_id=next_target.telegram_id)
        await cbmd(callback)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=next_target,
            is_owner=False,
            keyboard=build_rating_keyboard(),
        )

    # ------ СКИП ------
    elif action == "rate_skip":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if target_tg_id:
            target = db.get_user(target_tg_id)
            if target:
                db.edit_user(target_tg_id, skips=target.skips + 1)

        db.add_review(callback.from_user.id, target_tg_id)
        target = await get_next_profile_for_rating(user)
        if target == 0:
            await cbmd(callback)
            kb = repeatbutton(user)
            await callback.message.answer(
                "Анкет больше нет. Вы молодец! 🎉",
                reply_markup=kb
            )
            await state.clear()
            return
        else:

            await state.update_data(current_target_telegram_id=target.telegram_id)
            await cbmd(callback)
            await send_user_profile_with_photo(
                chat_id=callback.from_user.id,
                user=target,
                is_owner=False,
                keyboard=build_rating_keyboard(),
            )

    # ------ ЗАКОНЧИТЬ ОЦЕНКУ ------
    elif action == "rate_finish":
        await cbmd(callback)
        await state.clear()
        msg = await callback.message.answer("🏁 Вы завершили оценку анкет.")
        await asyncio.sleep(1)
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        await main_menu(callback.message, callback.from_user.id)

    # ------ ТЭГНУТЬ ПОЛЬЗОВАТЕЛЯ ------
    elif action == "rate_tag":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if not target_tg_id:
            await callback.answer("Ошибка: нет текущей анкеты.", show_alert=True)
            return

        if target_tg_id == callback.from_user.id:
            await callback.answer("Нельзя ставить теги самому себе.", show_alert=True)
            return

        await cbmd(callback)
        await callback.message.answer(
            "🏷 Выберите тег для этого пользователя:",
            reply_markup=build_tags_keyboard(target_tg_id)
        )

    # ------ ВЫБОР КОНКРЕТНОГО ТЕГА ------
    elif action.startswith("tag_apply:"):
        # Формат: tag_apply:{target_telegram_id}:{tag_id}
        try:
            _, target_tg_id_str, tag_id_str = action.split(":")
            target_tg_id = int(target_tg_id_str)
            tag_id = str(tag_id_str)
            tag = db.get_all_tags(tag_id=tag_id)[0]
            tag_name = tag.name
        except ValueError:
            await callback.answer("Неверный формат данных тега.", show_alert=True)
            return

        if target_tg_id == callback.from_user.id:
            await callback.answer("Нельзя ставить теги самому себе.", show_alert=True)
            return

        target = db.get_user(target_tg_id)
        if not target:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        added = 0
        deleted = 0
        if tag in db.get_tags_for_user(target.id):
            deleted = 1
        else:
            added = 1


        try:
            if added:
                text = f"⭐️ Вас оценили: @{callback.from_user.username} поставил(а) вам тэг: {tag_name}"
                # Используем user.id как внутренний id (FK в photos/tags)
                db.add_tag_to_user(user_id=target.id, tag_id=tag_id)
                await callback.answer("Тег добавлен ✅", show_alert=False)
            elif deleted:
                text = f"♻️ @{callback.from_user.username} убрал(а) тэг: {tag_name}"
                db.remove_tag_from_user(user_id=target.id, tag_id=tag_id)
                await callback.answer("Тег удалён ✅", show_alert=False)
            else:
                text = None

            if text:
                kb = closebutton()
                await bot.send_message(
                    chat_id=target_tg_id,
                    text=text,
                    reply_markup=kb
                )
        except Exception as e:
            print(f"Ошибка отправки уведомления о тэге: {e}")


        

        # Возвращаемся к оценке: показываем ту же анкету + клавиатуру
        await cbmd(callback)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=target,
            is_owner=False,
            keyboard=build_rating_keyboard(),
        )

    # ------ НАЗАД К ОЦЕНКЕ ИЗ МЕНЮ ТЕГОВ ------
    elif action == "back_to_rating":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if not target_tg_id:
            await callback.answer("Нет активной анкеты.", show_alert=True)
            return

        target = db.get_user(target_tg_id)
        if not target:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        await cbmd(callback)
        await send_user_profile_with_photo(
            chat_id=callback.from_user.id,
            user=target,
            is_owner=False,
            keyboard=build_rating_keyboard(),
        )
    
    # ------- НАПИСАТЬ СООБЩЕНИЕ -----------
    elif action == "write_user":
        data = await state.get_data()
        target_tg_id = data.get("current_target_telegram_id")
        if not target_tg_id:
            await callback.answer("Ошибка: нет текущей анкеты.", show_alert=True)
            return

        if target_tg_id == callback.from_user.id:
            await callback.answer("Нельзя писать самому себе.", show_alert=True)
            return

        await cbmd(callback)
        # сохраняем, кому пишем
        await state.update_data(dm_target_telegram_id=target_tg_id)
        await state.set_state(Form.WAITING_FOR_DM)

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⬅️ Назад к анкете",
                callback_data="back_to_rating"
            )
        )

        await callback.message.answer(
            "✉️ Отправьте текст сообщения для этого пользователя.\n\n"
            "Сообщение будет доставлено ему ботом.",
            reply_markup=builder.as_markup()
        )

    # ------ МОИ ТЕГИ (авторские) ------
    elif action == "my_tags":
        await cbmd(callback)
        # Теги, созданные этим юзером
        tags = db.get_tags_by_author(user.id)
        if not tags:
            msg = await callback.message.answer("У вас пока нет созданных тегов 🏷")
            await asyncio.sleep(1)
            try:
                await msg.delete()
            except TelegramBadRequest:
                pass
            await main_menu(callback.message, callback.from_user.id)
        else:
            builder = InlineKeyboardBuilder()
            for t in tags:
                builder.row(
                    InlineKeyboardButton(
                        text=f"🏷 {t.name}",
                        callback_data=f"delete_tag:{t.id}"
                    )
                )
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back"
                )
            )
            await callback.message.answer(
                "Ваши теги (нажмите на тег, чтобы удалить):",
                reply_markup=builder.as_markup()
            )

    # ------ УДАЛЕНИЕ СОБСТВЕННЫХ ТЕГОВ ------
    elif action.startswith("delete_tag:"): 
        await cbmd(callback)
        try:
            tag_id = int(action.split(":", 1)[1])
        except ValueError:
            await callback.answer("Некорректный тег.", show_alert=True)
            return

        ok = db.delete_tag(tag_id=tag_id, author_user_id=user.id)
        tags = db.get_tags_by_author(user.id)

        if not ok:
            kb = backbutton(user)
            await callback.message.answer(
                "Не удалось удалить тег (возможно, он уже удалён или не ваш).",
                reply_markup=kb
            )
            return

        if not tags:
            msg = await callback.message.answer("Все ваши теги удалены 🧹")
            await asyncio.sleep(1)
            try:
                await msg.delete()
            except TelegramBadRequest:
                pass
            await main_menu(callback.message, callback.from_user.id)
        else:
            builder = InlineKeyboardBuilder()
            for t in tags:
                builder.row(
                    InlineKeyboardButton(
                        text=f"🏷 {t.name}",
                        callback_data=f"delete_tag:{t.id}"
                    )
                )
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back")
            )
            await callback.message.answer(
                "Тег удалён. Ваши теги:",
                reply_markup=builder.as_markup()
            )

    # ------ СОЗДАТЬ ТЭГ  ------------
    elif action == "create_tag": 
        await cbmd(callback)

        if user.balance < 50:
            kb = backbutton(user)
            await callback.message.answer(
                "Недостаточно подсолнухов для создания тега. Нужно 50 🌻.",
                reply_markup=kb
            )
            return

        await callback.message.answer(
            "💡 Отправьте название тега.\n"
            "Можно указать описание через « - ».\n\n"
            "Пример: умный - отлично решает задачи"
        )
        await state.set_state(Form.WAITING_FOR_TAG_NAME)

    # ------ ПРИГЛАСИТЬ ------
    elif action == "invite":
        await cbmd(callback)
        link = await create_start_link(bot, str(callback.from_user.id))
        text = (
            "📡 <b>Пригласи друзей!</b>\n\n"
            "Отправь им эту ссылку, и за каждого, кто зайдёт через неё, "
            "ты получишь <b>10 🌻</b>.\n\n"
            f"<code>{link}</code>"
        )
        kb = backbutton(user)
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ------ ТОП ЮЗЕРОВ ------
    elif action == "top_users":
        await cbmd(callback)
        top = db.get_top_users(limit=10)

        kb = backbutton(user)

        if not top:
            await callback.message.answer(
                "🏆 Пока нет ни одной опубликованной анкеты с лайками.",
                reply_markup=kb
            )
            return

        lines = ["🏆 <b>Топ пользователей по лайкам</b>:\n"]
        place = 1
        for u in top:
            if u.username_hidden:
                uname = "Скрыто"
            else:
                uname = f"@{u.telegram_uname}" if u.telegram_uname else f"id{u.telegram_id}"
            
            lines.append(f"{place}. <b>{u.name}</b> ({uname}) — 👍 {u.liked}, 👎 {u.disliked}")
            place += 1

        text = "\n".join(lines)
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    # ------- ПЕРЕЗАПУСТИТЬ ЦИКЛ -----------
    elif action == "clear_reviews":
        db.clear_reviews(callback.from_user.id)
        user_id = int(callback.from_user.id)
        await cbmd(callback)
        try:
            await state.clear()
        except:
            pass
        await main_menu(callback.message, user_id)

    # ------ НАЗАД В МЕНЮ ------
    elif action == "back":
        user_id = int(callback.from_user.id)
        await cbmd(callback)
        await state.clear()
        await main_menu(callback.message, user_id)

    # ------ ПРОСТО ЗАКРЫТЬ СООБЩЕНИЕ ------
    elif action == "close":
        await cbmd(callback)

    return 0


# ====== ОБРАБОТКА ВВОДА БИО ======
@router.message(Form.WAITING_FOR_BIO)
async def process_bio(message: Message, state: FSMContext):
    new_bio = message.text.strip()
    if not new_bio:
        await message.answer("Описание не может быть пустым. Попробуйте ещё раз.")
        return

    db.edit_user(message.from_user.id, biography=new_bio)
    await message.answer("✅ Описание обновлено.")

    await state.clear()

    # Показываем обновлённую анкету
    user = db.get_user(message.from_user.id)
    keyboard = build_my_profile_keyboard(user)
    await send_user_profile_with_photo(
        chat_id=message.from_user.id,
        user=user,
        is_owner=True,
        keyboard=keyboard,
    )
    return 0


# ====== ОБРАБОТКА ФОТО ДЛЯ АНКЕТЫ ======
@router.message(Form.WAITING_FOR_PHOTO, F.photo)
async def process_photo(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start.")
        await state.clear()
        return

    data = await state.get_data()
    photo_mode = data.get("photo_mode", "add")

    # Берём самое большое по размеру фото
    photo = message.photo[-1]

    file_buffer = BytesIO()
    await bot.download(photo, destination=file_buffer)
    raw_bytes = file_buffer.getvalue()
    raw_b64 = base64.b64encode(raw_bytes).decode("utf-8")

    # Сохраняем фото (в текущей реализации мы не удаляем старые,
    # просто добавляем новое; отображается всегда последнее).
    db.add_photo(user_id=user.id, raw_png=raw_b64, description="avatar")

    if photo_mode == "change":
        text = "🖼 Фото анкеты обновлено ✅"
    elif photo_mode == "add":
        text = "🖼 Фото анкеты добавлено ✅"
    else:
        text = "🖼 Фото анкеты сохранено ✅"

    await message.answer(text)

    await state.clear()

    # Показываем анкету
    keyboard = build_my_profile_keyboard(user)
    await send_user_profile_with_photo(
        chat_id=message.from_user.id,
        user=user,
        is_owner=True,
        keyboard=keyboard,
    )

    return 0


# ====== ОБРАБОТКА СОЗДАНИЯ ТЕГА ======
@router.message(Form.WAITING_FOR_TAG_NAME)
async def process_tag_name(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Название тега не может быть пустым. Попробуйте ещё раз.")
        return

    if " - " in text:
        name, description = text.split(" - ", 1)
        name = name.strip()
        description = description.strip()
    else:
        name = text
        description = None

    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start.")
        await state.clear()
        return

    if len(name) > 20:
        kb = backbutton(user)
        await message.answer(
            "Слишком длинное имя тэга (>15 символов).",
            reply_markup=kb
        )
        await state.clear()
        return

    if user.balance < 50:
        kb = backbutton(user)
        await message.answer(
            "Недостаточно подсолнухов для создания тега. Нужно 50 🌻.",
            reply_markup=kb
        )
        await state.clear()
        return

    # создаём тег с автором
    tag = db.create_tag(
        name=name,
        description=description,
        author_user_id=user.id
    )

    # списываем 50 с баланса
    db.edit_user(message.from_user.id, balance=user.balance - 50)

    await state.clear()
    kb = backbutton(user)
    await message.answer(
        f"🏷 Тег <b>{tag.name}</b> создан! С вашего баланса списано 50 🌻.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )


# ====== ОБРАБОТКА ОТПРАВКИ ЛИЧНОГО СООБЩЕНИЯ ======
@router.message(Form.WAITING_FOR_DM)
async def process_direct_message(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Напишите что-нибудь 🙂")
        return

    data = await state.get_data()
    target_tg_id = data.get("dm_target_telegram_id") or data.get("current_target_telegram_id")
    if not target_tg_id:
        await message.answer("Ошибка: не найден получатель сообщения.")
        await state.clear()
        return

    sender = db.get_user(message.from_user.id)
    target = db.get_user(target_tg_id)
    if not sender or not target:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return

    # Формируем шапку с учётом настройки username_hidden
    if not sender.telegram_uname:
        header = f"💌 Вам сообщение от {sender.name} (id{sender.telegram_id}):"
    else:
        header = f"💌 Вам сообщение от @{sender.telegram_uname} ({sender.name}):"

    try:
        await bot.send_message(
            chat_id=target.telegram_id,
            text=f"{header}\n\n{text}",
            reply_markup=closebutton()
        )
    except Exception as e:
        print(f"Ошибка отправки личного сообщения: {e}")
        await message.answer("Не удалось доставить сообщение пользователю.")
        await state.set_state(Form.RATING)
        return

    # Для бесшовности — удаляем текстовое сообщение отправителя
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    await state.set_state(Form.RATING)
    await message.answer("✉️ Сообщение отправлено пользователю.", reply_markup=backbutton(sender))

    current_tg = data.get("current_target_telegram_id")
    if current_tg:
        u = db.get_user(current_tg)
        if u:
            await send_user_profile_with_photo(
                chat_id=message.from_user.id,
                user=u,
                is_owner=False,
                keyboard=build_rating_keyboard(),
             )

    return 0