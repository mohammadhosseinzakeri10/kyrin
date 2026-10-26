"""STT admission at the engine/session contract, outside audio acquisition."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat
from kyrin.model_resources import ModelResources, ResourceUnavailable, Workload
from kyrin.stt.contracts import (
    SpeechToTextEngine,
    SpeechToTextSession,
    TurnAwareSpeechToTextSession,
)
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.transcript import TranscriptUpdate


class ManagedSttEngine:
    """Pin the selected STT model until real engine shutdown, across turns."""

    def __init__(
        self,
        open_engine: Callable[[], SpeechToTextEngine],
        resources: ModelResources,
        key: str,
    ) -> None:
        self._resources, self._key = resources, key
        with self._admit(keep_resident=True):
            self._engine = open_engine()
        self.capabilities = self._engine.capabilities

    @contextmanager
    def _admit(self, *, keep_resident: bool = False) -> Iterator[None]:
        try:
            with self._resources.use(
                Workload.STT, self._key, keep_resident=keep_resident
            ):
                yield
        except ResourceUnavailable as exc:
            raise SpeechToTextError(str(exc)) from exc

    def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
        with self._admit():
            session = self._engine.open_session(options)
        if isinstance(session, TurnAwareSpeechToTextSession):
            return _ManagedTurnSession(session, self)
        return _ManagedSession(session, self)

    def close(self) -> None:
        # Shutdown/cancellation must bypass admission, especially if inference owns it.
        self._engine.close()
        self._resources.forget(self._key)

    def cancel_pending_inference(self) -> None:
        cancel = getattr(self._engine, "cancel_pending_inference", None)
        if callable(cancel):
            cancel()
        # Keep accounting until close confirms resource release.


class _ManagedSession:
    def __init__(self, session: SpeechToTextSession, engine: ManagedSttEngine) -> None:
        self._session, self._engine = session, engine

    @property
    def input_format(self) -> AudioFormat:
        return self._session.input_format

    @property
    def compute_device(self) -> ComputeDevice:
        return self._session.compute_device

    @property
    def supports_partial_updates(self) -> bool:
        return self._session.supports_partial_updates

    def _handoff(
        self, updates: Sequence[TranscriptUpdate]
    ) -> Sequence[TranscriptUpdate]:
        for update in updates:
            if update.retained_audio is not None:
                update.retained_audio.bind_admission(self._engine._admit)
        return updates

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        with self._engine._admit():
            return self._handoff(self._session.accept_audio(chunk))

    def finish(self) -> Sequence[TranscriptUpdate]:
        with self._engine._admit():
            return self._handoff(self._session.finish())

    def close(self) -> None:
        self._session.close()


class _ManagedTurnSession(_ManagedSession):
    def start_turn(self) -> Sequence[TranscriptUpdate]:
        assert isinstance(self._session, TurnAwareSpeechToTextSession)
        with self._engine._admit():
            return self._handoff(self._session.start_turn())

    def end_turn(self) -> Sequence[TranscriptUpdate]:
        assert isinstance(self._session, TurnAwareSpeechToTextSession)
        with self._engine._admit():
            return self._handoff(self._session.end_turn())
