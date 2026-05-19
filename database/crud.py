from typing import Dict, List, Optional
from datetime import datetime, timezone

from sqlmodel import Session, select, col
from sqlalchemy import Engine

from models import TelegramMessage, Location, MediaProcessingJob, PipelineStatus, PlatformType

def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)

class DatabaseCRUD:
    def __init__(self, engine: Engine):
        self.engine = engine

    # ----------------------------------------
    #   Location Methods
    # ----------------------------------------
    
    def get_location(self, location_id: str) -> Location | None:
        with Session(self.engine) as session:
            return session.get(Location, location_id)
    
    def get_all_locations(self) -> Dict[str, Location]:
        with Session(self.engine) as session:
            results = session.exec(select(Location)).all()
            return {loc.id: loc for loc in results}

    def insert_location(self, location: Location) -> Location:
        with Session(self.engine) as session:
            session.add(location)
            session.commit()
            session.refresh(location)
            session.expunge(location)
            return location

    def update_location(self, location: Location) -> Location:
        with Session(self.engine) as session:
            existing = session.get(Location, location.id)
            if not existing:
                raise ValueError(f"Location {location.id} non trovata.")
            
            merged_location = session.merge(location)
            session.commit()
            session.refresh(merged_location)
            session.expunge(merged_location)
            return merged_location

    def delete_location(self, location_id: str) -> None:
        with Session(self.engine) as session:
            location = session.get(Location, location_id)
            if location:
                session.delete(location)
                session.commit()

    def get_location_by_place_id(self, google_place_id: str) -> Location | None:
        """Sostituisce il vecchio 'get_location_by_checksum' usando il Place ID di Google"""
        with Session(self.engine) as session:
            statement = select(Location).where(Location.google_place_id == google_place_id)
            return session.exec(statement).first()

    # ----------------------------------------
    #   Telegram Message Methods
    # ----------------------------------------

    def get_messages(self) -> List[TelegramMessage]:
        with Session(self.engine) as session:
            statement = select(TelegramMessage).order_by(col(TelegramMessage.timestamp))
            return list(session.exec(statement).all())

    def get_telegram_message(self, chat_id: int, telegram_id: int) -> TelegramMessage | None:
        """
        NOTA BENE: Ora cerca per chat_id E telegram_id per via del vincolo di univocità.
        """
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(
                TelegramMessage.chat_id == chat_id,
                TelegramMessage.telegram_id == telegram_id
            )
            return session.exec(statement).first()

    def upsert_telegram_message(self, message: TelegramMessage) -> TelegramMessage:
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(
                TelegramMessage.chat_id == message.chat_id,
                TelegramMessage.telegram_id == message.telegram_id
            )
            existing_message = session.exec(statement).first()
            
            if existing_message:
                existing_message.raw_text = message.raw_text
                # Non sovrascrivere lo status se precedentemente processato
                existing_message.platform_detected = message.platform_detected
                session.add(existing_message)
                session.commit()
                session.refresh(existing_message)
                session.expunge(existing_message)
                return existing_message
            else:
                session.add(message)
                session.commit()
                session.refresh(message)
                session.expunge(message)
                return message

    def get_unprocessed_messages(self, status: PipelineStatus = PipelineStatus.IMPORTED) -> List[TelegramMessage]:
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(TelegramMessage.status == status)
                .order_by(col(TelegramMessage.timestamp))
            )
            return list(session.exec(statement).all())

    def update_message_status(
        self, message_id: int, status: PipelineStatus
    ) -> None:
        """Aggiorna lo stato. Usa message_id (ID primario del DB), non il telegram_id."""
        with Session(self.engine) as session:
            message = session.get(TelegramMessage, message_id)
            if message:
                message.status = status
                if status in[PipelineStatus.DONE, PipelineStatus.FAILED, PipelineStatus.DISCARDED]:
                    message.processed_at = get_utc_now()
                
                session.add(message)
                session.commit()

    def update_message_platform(self, message_id: int, platform: PlatformType) -> None:
        """Aggiorna il platform_detected di un messaggio."""
        with Session(self.engine) as session:
            message = session.get(TelegramMessage, message_id)
            if message:
                message.platform_detected = platform
                session.add(message)
                session.commit()

    # ----------------------------------------
    #   Media Processing Job
    # ----------------------------------------

    def get_media_job(self, message_id: int) -> MediaProcessingJob | None:
        """Recupera il Job associato a un messaggio Telegram."""
        with Session(self.engine) as session:
            statement = select(MediaProcessingJob).where(MediaProcessingJob.message_id == message_id)
            return session.exec(statement).first()

    def get_media_job_by_source_url(self, source_url: str) -> MediaProcessingJob | None:
        """Recupera il Job associato a un URL sorgente (es. Reel Instagram)."""
        with Session(self.engine) as session:
            statement = select(MediaProcessingJob).where(MediaProcessingJob.source_url == source_url)
            return session.exec(statement).first()

    def upsert_media_job(self, job: MediaProcessingJob) -> MediaProcessingJob:
        with Session(self.engine) as session:
            existing = self.get_media_job(job.message_id)
            
            job.updated_at = get_utc_now()
            
            if existing:
                # Copia i valori del nuovo job su quello esistente
                job.id = existing.id
                merged_job = session.merge(job)
            else:
                merged_job = job
                session.add(merged_job)
                
            session.commit()
            session.refresh(merged_job)
            session.expunge(merged_job)
            return merged_job

    def get_jobs_by_status(self, download_status: Optional[str] = None, ai_status: Optional[str] = None) -> List[MediaProcessingJob]:
        """Esempio: Trova tutti i video in attesa di elaborazione AI."""
        with Session(self.engine) as session:
            statement = select(MediaProcessingJob)
            if download_status:
                statement = statement.where(MediaProcessingJob.download_status == download_status)
            if ai_status:
                statement = statement.where(MediaProcessingJob.ai_status == ai_status)
                
            return list(session.exec(statement).all())

     # ----------------------------------------
    #   Funzioni specifiche (Business Logic)
    # ----------------------------------------

    def get_latest_telegram_message(self, chat_id: int) -> TelegramMessage | None:
        """Recupera l'ultimo messaggio di una determinata chat."""
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(TelegramMessage.chat_id == chat_id)
                # Usa col() per risolvere l'errore di typing
                .order_by(col(TelegramMessage.timestamp).desc())
            )
            return session.exec(statement).first()

    def get_telegram_messages_since(self, chat_id: int, since: datetime) -> List[TelegramMessage]:
        """Recupera i messaggi da una certa data in poi."""
        with Session(self.engine) as session:
            statement = (
                select(TelegramMessage)
                .where(
                    (TelegramMessage.chat_id == chat_id) &
                    (TelegramMessage.timestamp >= since)
                )
                .order_by(col(TelegramMessage.timestamp))
            )
            return list(session.exec(statement).all())

    def get_messages_without_category(self) -> List[TelegramMessage]:
        """Recupera i messaggi che non sono ancora stati analizzati (categoria UNKNOWN)."""
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(
                TelegramMessage.platform_detected == PlatformType.UNKNOWN
            )
            return list(session.exec(statement).all())

    def get_messages_by_platform(self, platform: PlatformType) -> List[TelegramMessage]:
        """
        L'equivalente del tuo vecchio get_messages_by_category.
        Esempio: get_messages_by_platform(PlatformType.INSTAGRAM)
        """
        with Session(self.engine) as session:
            statement = select(TelegramMessage).where(
                TelegramMessage.platform_detected == platform
            )
            return list(session.exec(statement).all())

    def get_reprocessable_instagram_messages(self, statuses: Optional[List[PipelineStatus]] = None) -> List[TelegramMessage]:
        """
        Cerca messaggi legati a Instagram (sia per Enum che per regex nel testo) 
        per un eventuale ricalcolo.
        """
        with Session(self.engine) as session:
            # col() è utilissimo anche con .contains()
            instagram_like = (
            (col(TelegramMessage.platform_detected) == PlatformType.INSTAGRAM) |
            col(TelegramMessage.raw_text).contains("instagram.com/reel") |
            col(TelegramMessage.raw_text).contains("instagram.com/p/") |
            col(TelegramMessage.raw_text).contains("instagr.am")
        )

            statement = select(TelegramMessage).where(instagram_like)

            if statuses:
                statement = statement.where(col(TelegramMessage.status).in_(statuses))

            statement = statement.order_by(col(TelegramMessage.timestamp))
            return list(session.exec(statement).all())

    def has_location_for_source_url(self, source_url: str) -> bool:
        """
        Verifica se abbiamo già salvato una Location partendo da un URL specifico (es. link del Reel).
        Con i nuovi modelli, facciamo una JOIN tra Location, Messaggio e MediaProcessingJob.
        """
        with Session(self.engine) as session:
            statement = (
                select(Location)
                .join(TelegramMessage)
                .join(MediaProcessingJob)
                .where(MediaProcessingJob.source_url == source_url)
            )
            return session.exec(statement).first() is not None