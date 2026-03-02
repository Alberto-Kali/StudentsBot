from sqlalchemy.orm import sessionmaker
from database import init_db, Tags, UsersTags, Users, Photos, UserRatings, UserReviewedUser
from datetime import datetime
import uuid

from sqlalchemy.exc import SQLAlchemyError

from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from database import init_db, Tags, UsersTags, Users, Photos


class DBControl:
    def __init__(self, db_uri=None):

        if db_uri is None:
            db_uri = 'clickhouse://default:TupayaFrigitnaya12312@192.168.2.237:18123/uebki39bot'
        
        engine = init_db(db_uri)
        Session = sessionmaker(bind=engine)
        self.session = Session()
        self.engine = engine


    # ============ RATINGS ============

    def get_user_rating(self, rater_tg: int, target_tg: int):
        """Возвращает голос rater -> target или None."""
        return (
            self.session.query(UserRatings)
            .filter_by(rater_telegram_id=rater_tg, target_telegram_id=target_tg)
            .first()
        )

    def rate_user(self, rater_tg: int, target_tg: int, value: int):
        """
        Поставить/изменить оценку:
        value: 1 = лайк, -1 = дизлайк
        Возвращает (target_user, is_new, changed)
        """
        if rater_tg == target_tg:
            return None, False, False

        target = self.get_user(target_tg)
        if not target:
            return None, False, False

        rating = self.get_user_rating(rater_tg, target_tg)
        is_new = False
        changed = False

        if rating is None:
            # первая оценка
            rating = UserRatings(
                rater_telegram_id=rater_tg,
                target_telegram_id=target_tg,
                value=value,
            )
            self.session.add(rating)
            is_new = True

            if value == 1:
                target.liked += 1
            elif value == -1:
                target.disliked += 1

        else:
            # уже есть голос
            if rating.value == value:
                # ничего не меняется
                self.session.commit()
                return target, False, False

            # меняем оценку
            old = rating.value
            rating.value = value
            changed = True

            if old == 1:
                target.liked -= 1
            elif old == -1:
                target.disliked -= 1

            if value == 1:
                target.liked += 1
            elif value == -1:
                target.disliked += 1

        self.session.commit()
        return target, is_new, changed

    def get_top_users(self, limit: int = 10):
        """Топ пользователей по лайкам (только опубликованные и не забаненные)."""
        return (
            self.session.query(Users)
            .filter(Users.published == 1, Users.banned == 0)
            .order_by(Users.liked.desc())
            .limit(limit)
            .all()
        )



    # ============ USERS ============

    def get_user_by_telegram_id(self, telegram_id: int):
        """Возвращает пользователя по telegram_id (или None)."""
        return self.session.query(Users).filter_by(telegram_id=telegram_id).first()

    def get_user_byid(self, user_id):
        return self.session.query(Users).filter_by(id=user_id).first()

    def get_user(self, telegram_id: int):
        """Синоним get_user_by_telegram_id для удобства."""
        return self.get_user_by_telegram_id(telegram_id)

    def create_user(self, name: str, telegram_uname: str, telegram_id: int, biography: str = None):
        """Создаёт нового пользователя."""
        try:
            user = Users(
                name=name,
                telegram_uname=telegram_uname,
                telegram_id=telegram_id,
                biography=biography,
            )
            self.session.add(user)
            self.session.commit()
            return user
        except SQLAlchemyError as e:
            self.session.rollback()
            raise e

    def add_user(self, name: str, telegram_uname: str, telegram_id: int, biography: str = None):
        """Обёртка над create_user (на случай, если где-то вызывается add_user)."""
        return self.create_user(name=name, telegram_uname=telegram_uname, telegram_id=telegram_id, biography=biography)

    def edit_user(self, telegram_id: int, **fields):
        """
        Обновляет поля пользователя по telegram_id.
        Пример: edit_user(12345, biography='Новый текст', balance=50)
        """
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            return None

        for key, value in fields.items():
            if hasattr(user, key):
                setattr(user, key, value)
        self.session.commit()
        return user

    def update_user_visibility(self, telegram_id: int, published: bool):
        """Специальный метод для изменения флага published."""
        user = self.get_user_by_telegram_id(telegram_id)
        if user:
            user.published = 1 if published else 0
            self.session.commit()
            return user
        return None

    def delete_user(self, telegram_id: int):
        """Жёсткое удаление пользователя (для ClickHouse не лучший вариант, но оставим)."""
        user = self.get_user_by_telegram_id(telegram_id)
        if user:
            self.session.delete(user)
            self.session.commit()
            return True
        return False

    def get_random_published_user(self, exclude_telegram_id: int | None = None):
        """
        Возвращает случайного опубликованного и не забаненного пользователя.
        Можно исключить текущего по telegram_id.
        """
        query = self.session.query(Users).filter(
            Users.published == 1,
            Users.banned == 0,
        )
        exclude_reviewed_ids = self.list_reviewed(exclude_telegram_id)
        #print(exclude_reviewed_ids)
        if exclude_telegram_id is not None:
            query = query.filter(Users.telegram_id != exclude_telegram_id)
        
        if exclude_reviewed_ids:
            # NOT IN по SQL, а не "not in" по Python
            query = query.filter(~Users.telegram_id.in_(exclude_reviewed_ids))

        # ClickHouse поддерживает функцию rand()
        user = query.order_by(func.rand()).first()
        try:
            uid = user.id
            return user
        except:
            return 0


    # ============ TAGS ============

    def create_tag(self, name: str, description: str = None, author_user_id=None):
        """Создаёт новый тег с автором (author_user_id = Users.id)."""
        # author_user_id у тебя — Users.id (UUID как строка)
        if isinstance(author_user_id, uuid.UUID):
            author_user_id = str(author_user_id)

        tag = Tags(name=name, description=description, author_user_id=author_user_id)
        self.session.add(tag)
        self.session.commit()
        return tag

    def get_all_tags(self, tag_id=None):
        """Все теги (для выбора при тэггинге других)."""
        if not tag_id:
            return self.session.query(Tags).all()
        else:
            return self.session.query(Tags).filter_by(id=tag_id).all()

    def get_tags_for_user(self, user_id):
        """Теги, привязанные к анкете пользователя (старый функционал)."""
        if isinstance(user_id, uuid.UUID):
            user_id = str(user_id)

        return (
            self.session.query(Tags)
            .join(UsersTags, Tags.id == UsersTags.tag_id)
            .filter(UsersTags.user_id == user_id)
            .all()
        )


    def add_tag_to_user(self, user_id, tag_id):
        """Повесить тег на пользователя (оценка/тэггинг) с лимитом 5 тегов.
        
        Если после добавления тега их становится > 5, удаляем все старые
        и оставляем только текущий тег.
        """

        # нормализуем UUID в строки, чтобы не ловить Unsupported object
        if isinstance(user_id, uuid.UUID):
            user_id = str(user_id)
        if isinstance(tag_id, uuid.UUID):
            tag_id = str(tag_id)

        # все существующие связи для пользователя
        existing_links = (
            self.session.query(UsersTags)
            .filter_by(user_id=user_id)
            .all()
        )

        # если такой тег уже стоит — просто возвращаем связь
        for link in existing_links:
            if str(link.tag_id) == str(tag_id):
                return link

        # если тэгов уже 5 или больше — чистим ВСЕ и оставляем только новый
        if len(existing_links) >= 7:
            for link in existing_links:
                self.session.delete(link)
            # не коммитим здесь, чтобы всё ушло в одной транзакции

        # создаём новую связь
        ut = UsersTags(user_id=user_id, tag_id=tag_id)
        self.session.add(ut)
        self.session.commit()
        return ut


    def remove_tag_from_user(self, user_id, tag_id) -> bool:
        if isinstance(user_id, uuid.UUID):
            user_id = str(user_id)
        if isinstance(tag_id, uuid.UUID):
            tag_id = str(tag_id)

        ut = self.session.query(UsersTags).filter_by(user_id=user_id, tag_id=tag_id).first()
        if ut:
            self.session.delete(ut)
            self.session.commit()
            return True
        return False

    def get_tags_by_author(self, author_user_id):
        if isinstance(author_user_id, uuid.UUID):
            author_user_id = str(author_user_id)

        return self.session.query(Tags).filter_by(author_user_id=author_user_id).all()

    def delete_tag(self, tag_id, author_user_id) -> bool:
        if isinstance(tag_id, uuid.UUID):
            tag_id = str(tag_id)
        if isinstance(author_user_id, uuid.UUID):
            author_user_id = str(author_user_id)

        tag = (
            self.session.query(Tags)
            .filter_by(id=tag_id, author_user_id=author_user_id)
            .first()
        )
        if not tag:
            return False

        self.session.query(UsersTags).filter_by(tag_id=tag_id).delete()
        self.session.delete(tag)
        self.session.commit()
        return True


    # ============ PHOTOS ============

    def add_photo(self, user_id: int, raw_png: str, description: str = None):
        """
        Добавляет фото пользователю (user_id — это Users.id, raw_png — строка base64 PNG).
        """
        photo = Photos(user_id=user_id, raw_png=raw_png, description=description)
        self.session.add(photo)
        self.session.commit()
        return photo

    def get_photos_for_user(self, user_id: int):
        """Возвращает все фото пользователя по его внутреннему id."""
        return self.session.query(Photos).filter_by(user_id=user_id).all()

    def delete_photo(self, photo_id: int):
        """Удаляет фото по его id."""
        photo = self.session.query(Photos).filter_by(id=photo_id).first()
        if photo:
            self.session.delete(photo)
            self.session.commit()
            return True
        return False

    # ============ REVIEWS ==============

    def add_review(self, user_id: int, rev_id: int):

        uid = self.get_user_by_telegram_id(user_id).id
        rid = self.get_user_by_telegram_id(rev_id).id
        try:
            rev = UserReviewedUser(
                user_id=uid,
                reviewed=rid
            )
            self.session.add(rev)
            self.session.commit()
            return rev
        except SQLAlchemyError as e:
            self.session.rollback()
            raise e


    def list_reviewed(self, user_id: int):
        uid = self.get_user_by_telegram_id(user_id).id
        return [self.get_user_byid(a.reviewed).telegram_id for a in self.session.query(UserReviewedUser).filter_by(user_id=uid).all()]



    def clear_reviews(self, user_id: int) -> int:
        """
        Удаляет все записи о просмотренных/оценённых анкетах для пользователя
        с заданным telegram_id.

        Возвращает количество удалённых записей.
        """
        uid = self.get_user_by_telegram_id(user_id).id

        try:
            q = self.session.query(UserReviewedUser).filter_by(user_id=uid)
            deleted_count = q.delete(synchronize_session=False)
            self.session.commit()
            return deleted_count
        except SQLAlchemyError as e:
            self.session.rollback()
            raise e


    # Close session
    def close(self):
        self.session.close()
