from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

from models.location import Location
from models.telegram_message import TelegramMessage
from models.instagram_reel import InstagramReel
# from models.tracemoeResponse import TracemoeResponse

class Database:

    def __init__(self, db_path: str = "sqlite:///data/database.db"):
        if db_path == "sqlite:////data/database.db":
            db_path = "sqlite:///data/database.db"

        if db_path.startswith("sqlite:///"):
            raw_path = db_path[len("sqlite:///"):]
            sqlite_file = Path(raw_path)
            if not sqlite_file.is_absolute():
                sqlite_file = (Path.cwd() / sqlite_file).resolve()
            sqlite_file.parent.mkdir(parents=True, exist_ok=True)
            db_path = f"sqlite:///{sqlite_file.as_posix()}"

        # Only use check_same_thread for SQLite
        if db_path.startswith("sqlite"):
            self.engine = create_engine(db_path, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(db_path)
        self._create_tables()

    def _create_tables(self):
        SQLModel.metadata.create_all(self.engine)
        self._migrate_sqlite_schema()

    def _migrate_sqlite_schema(self):
        if self.engine.url.get_backend_name() != "sqlite":
            return

        with self.engine.begin() as conn:
            columns = conn.exec_driver_sql("PRAGMA table_info(location)").fetchall()
            column_names = {column[1] for column in columns}

            if "google_maps_url" not in column_names:
                conn.exec_driver_sql("ALTER TABLE location ADD COLUMN google_maps_url TEXT")

#----------------------------------------
#   Location Methods
#----------------------------------------
    
    def location_exists(self, id: str) -> bool:
        """
        DEPRECATED: USE get_location INSTEAD

        Check if a location exists in the database.

        Args:
            id (str): The location ID to check

        Returns:
            bool: True if location exists, False otherwise
        """
        return self.get_location(id) is not None
    
    def get_location(self, location_id: str) -> Location | None:
        """
        Retrieve a single location by its ID.

        Args:
            id (str): The location ID to retrieve

        Returns:
            Location: The location object if found, None otherwise
        """
        with Session(self.engine) as session:
            statement = select(Location).where(Location.id == location_id)
            result = session.exec(statement).first()
           
            return result
    
    def get_locations(self) -> Dict[str, Location]:
        """
        Retrieve all locations from the database.

        Returns:
            Dict[str, Location]: Dictionary of all locations with their IDs as keys
        """
        with Session(self.engine) as session:
            statement = select(Location)
            results = session.exec(statement).all()
            
            return {location.id: location for location in results}

    def update_location(self, location: Location) -> Location:
        """
        Update an existing location in the database.

        Args:
            location (Location): The location object with updated data

        Returns:
            Location: The updated location object

        Raises:
            ValueError: If the location does not exist
        """
        with Session(self.engine) as session:
            existing_location = session.get(Location, location.id)
            if existing_location is None:
                raise ValueError(f"Location with id {location.id} does not exist. Use insert_location instead.")

            location = session.merge(location)

            merged_location = session.merge(location)
            session.commit()
            session.refresh(merged_location)
            session.expunge(merged_location)

            return merged_location
    
    def insert_location(self, location: Location) -> Location:
        """
        Insert a new location into the database.

        Args:
            location (Location): The location object to insert

        Returns:
            Location: The inserted location object

        Raises:
            ValueError: If a location with the same ID already exists
        """
        with Session(self.engine) as session:
            existing_location = session.get(Location, location.id)
            if existing_location is not None:
                raise ValueError(f"Location with id {location.id} already exists. Use update_location instead.")

            session.add(location)
            session.commit()
            session.refresh(location)
            session.expunge(location)

            return location

    def delete_location(self, id: str) -> None:
        """
        Delete a location and its associated media and TracemoeResponse from the database.

        Args:
            id (str): The ID of the location to delete
        """
        with Session(self.engine) as session:
            location = session.get(Location, id)
            if location:

                # Delete the location itself
                session.delete(location)
                session.commit()


#----------------------------------------
#   Telegram Message Methods
#----------------------------------------

    def get_telegram_message(self, telegram_id: int) -> TelegramMessage | None:
        """
        Retrieve a single Telegram message by its Telegram ID.

        Args:
            telegram_id (int): The Telegram message ID

        Returns:
            TelegramMessage: The message object if found, None otherwise
        """
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(TelegramMessage.telegram_id == telegram_id)
            result = session.exec(statement).first()
            return result

    def insert_telegram_message(self, message: TelegramMessage) -> TelegramMessage:
        """
        Insert a new Telegram message into the database.

        Args:
            message (TelegramMessage): The message object to insert

        Returns:
            TelegramMessage: The inserted message object

        Raises:
            ValueError: If a message with the same telegram_id already exists
        """
        with Session(self.engine) as session:
            existing_message = self.get_telegram_message(message.telegram_id)
            if existing_message is not None:
                raise ValueError(f"Message with telegram_id {message.telegram_id} already exists.")

            session.add(message)
            session.commit()
            session.refresh(message)
            session.expunge(message)

            return message

    def upsert_telegram_message(self, message: TelegramMessage) -> TelegramMessage:
        """
        Insert or update a Telegram message (idempotent).
        If the message already exists (by telegram_id), update it.
        Otherwise, insert it as new.

        Args:
            message (TelegramMessage): The message object to insert or update

        Returns:
            TelegramMessage: The inserted or updated message object
        """
        with Session(self.engine) as session:
            existing_message = self.get_telegram_message(message.telegram_id)
            if existing_message is not None:
                # Update existing message
                existing_message.raw_text = message.raw_text
                existing_message.extracted_data = message.extracted_data
                existing_message.status = message.status
                session.merge(existing_message)
                session.commit()
                session.refresh(existing_message)
                session.expunge(existing_message)
                return existing_message
            else:
                # Insert new message
                session.add(message)
                session.commit()
                session.refresh(message)
                session.expunge(message)
                return message

    def get_latest_telegram_message(self, chat_id: int) -> TelegramMessage | None:
        """
        Retrieve the latest Telegram message from a specific chat.

        Args:
            chat_id (int): The chat/group ID

        Returns:
            TelegramMessage: The latest message found, or None if no messages exist
        """
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(TelegramMessage.chat_id == chat_id)
                .order_by(TelegramMessage.timestamp.desc())
            )
            result = session.exec(statement).first()
            return result

    def get_telegram_messages_since(self, chat_id: int, since: datetime) -> List[TelegramMessage]:
        """
        Retrieve all Telegram messages from a chat after a specific timestamp.

        Args:
            chat_id (int): The chat/group ID
            since (datetime): The starting timestamp

        Returns:
            List[TelegramMessage]: List of messages after the timestamp, ordered by time
        """
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(
                    (TelegramMessage.chat_id == chat_id) &
                    (TelegramMessage.timestamp >= since)
                )
                .order_by(TelegramMessage.timestamp)
            )
            results = session.exec(statement).all()
            return results

    def get_unprocessed_messages(self, status: str = "imported") -> List[TelegramMessage]:
        """
        Retrieve all Telegram messages with a specific status (default: "imported").
        Used to find messages that need processing by workers.

        Args:
            status (str): The status to filter by (default: "imported")

        Returns:
            List[TelegramMessage]: List of unprocessed messages
        """
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(TelegramMessage.status == status)
                .order_by(TelegramMessage.timestamp)
            )
            results = session.exec(statement).all()
            return results

    def get_reprocessable_instagram_messages(self, statuses: Optional[List[str]] = None) -> List[TelegramMessage]:
        """
        Retrieve Instagram-related messages that can be reprocessed retroactively.

        A message is considered Instagram-related if:
        - category is already "instagram", or
        - raw_text contains a known Instagram post/reel URL pattern.

        Args:
            statuses (Optional[List[str]]): Optional list of statuses to include.
                Example: ["processed", "needs_review", "discarded"].
                If None or empty, no status filter is applied.

        Returns:
            List[TelegramMessage]: Candidate messages ordered by timestamp.
        """
        with Session(self.engine) as session:
            instagram_like = (
                (TelegramMessage.category == "instagram") |
                TelegramMessage.raw_text.contains("instagram.com/reel") |
                TelegramMessage.raw_text.contains("instagram.com/p/") |
                TelegramMessage.raw_text.contains("instagr.am")
            )

            statement = select(TelegramMessage).where(instagram_like)

            if statuses:
                statement = statement.where(TelegramMessage.status.in_(statuses))

            statement = statement.order_by(TelegramMessage.timestamp)
            results = session.exec(statement).all()
            return results

    def get_messages_without_category(self) -> List[TelegramMessage]:
        """
        Retrieve all Telegram messages that don't have a category assigned (category is NULL).
        Used to find messages that need categorization.

        Returns:
            List[TelegramMessage]: List of messages with category = None
        """
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(TelegramMessage.category == None)
            results = session.exec(statement).all()
            return results

    def update_message_status(self, telegram_id: int, status: str, processed_at: Optional[datetime] = None, category: Optional[str] = None) -> None:
        """
        Update the status and optionally the category of a Telegram message.

        Args:
            telegram_id (int): The Telegram message ID
            status (str): New status ("imported", "categorized", "processed", "done", "discarded")
            processed_at (datetime): When the message was completed (defaults to now if status is "processed" or "done")
            category (str): Message category ("instagram", "maps", "address", "random")
        """
        with Session(self.engine) as session:
            message = session.exec(select(TelegramMessage).where(TelegramMessage.telegram_id == telegram_id)).first()
            if message:
                message.status = status
                if category:
                    message.category = category
                if processed_at is None and status in ["processed", "done", "discarded", "needs_review"]:
                    message.processed_at = datetime.utcnow()
                else:
                    message.processed_at = processed_at
                session.add(message)
                session.commit()

    def has_location_for_source_url(self, source_url: str) -> bool:
        """
        Check whether at least one Location was saved for a given source URL.

        Args:
            source_url (str): Original message/reel source URL

        Returns:
            bool: True if at least one location exists for this source URL
        """
        with Session(self.engine) as session:
            statement = select(Location).where(Location.source_url == source_url)
            result = session.exec(statement).first()
            return result is not None

    def get_location_by_checksum(self, checksum: str) -> Location | None:
        """
        Retrieve a Location by its checksum (for deduplication).

        Args:
            checksum (str): The checksum hash

        Returns:
            Location: The location object if found, None otherwise
        """
        with Session(self.engine) as session:
            statement = select(Location).where(Location.checksum == checksum)
            result = session.exec(statement).first()
            return result


    def get_messages_by_category(self, category: str) -> List[TelegramMessage]:
        """
        Retrieve all Telegram messages that belong to a specific category.

        Args:
            category (str): The category to filter by (e.g., "instagram", "maps", "address", "random")

        Returns:
            List[TelegramMessage]: List of messages in the specified category
        """
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(TelegramMessage.category == category)
            results = session.exec(statement).all()
            return list(results)

#----------------------------------------
#   Instagram Reel Methods
#----------------------------------------

    def get_instagram_reel_by_telegram_id(self, telegram_id: int) -> InstagramReel | None:
        """
        Retrieve an InstagramReel snapshot by telegram_id.

        Args:
            telegram_id (int): Telegram message ID

        Returns:
            InstagramReel | None: snapshot if found
        """
        with Session(self.engine) as session:
            statement = select(InstagramReel).where(InstagramReel.telegram_id == telegram_id)
            result = session.exec(statement).first()
            return result
    def get_reels_by_pipeline_status(self, pipeline_status: str) -> List[InstagramReel]:
        """
        Retrieve all InstagramReel objects that are at a specific stage in the pipeline.
        
        Args:
            pipeline_status (str): The status to filter by
            
        Returns:
            List[InstagramReel]: List of reels matching the pipeline status
        """
        with Session(self.engine) as session:
            statement = select(InstagramReel).where(InstagramReel.pipeline_status == pipeline_status)
            results = session.exec(statement).all()
            return list(results)
    def upsert_instagram_reel(self, reel: InstagramReel) -> InstagramReel:
        """
        Insert or update InstagramReel snapshot by telegram_id.

        Args:
            reel (InstagramReel): Snapshot object

        Returns:
            InstagramReel: persisted snapshot
        """
        with Session(self.engine) as session:
            existing = session.exec(
                select(InstagramReel).where(InstagramReel.telegram_id == reel.telegram_id)
            ).first()

            if existing:
                existing.source_url = reel.source_url
                existing.shortcode = reel.shortcode
                existing.extraction_method = reel.extraction_method
                existing.pipeline_status = reel.pipeline_status
                existing.name = reel.name
                existing.description = reel.description
                existing.uploader = reel.uploader
                existing.video_path = reel.video_path
                existing.video_download_status = reel.video_download_status
                existing.ocr_text = reel.ocr_text
                existing.ocr_status = reel.ocr_status
                existing.audio_transcript = reel.audio_transcript
                existing.asr_status = reel.asr_status
                existing.ai_source = reel.ai_source
                existing.ai_status = reel.ai_status
                existing.ai_places_json = reel.ai_places_json
                existing.raw_payload = reel.raw_payload
                existing.extracted_at = reel.extracted_at
                existing.updated_at = datetime.utcnow()

                session.add(existing)
                session.commit()
                session.refresh(existing)
                session.expunge(existing)
                return existing

            reel.updated_at = datetime.utcnow()
            session.add(reel)
            session.commit()
            session.refresh(reel)
            session.expunge(reel)
            return reel