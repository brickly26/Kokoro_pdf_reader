from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QObject, Signal, QUrl

class AudioPlayer(QObject):
    playbackFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.player.mediaStatusChanged.connect(self._on_status)

    def play_file(self, path: str):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def stop(self):
        self.player.stop()

    def _on_status(self, st):
        # QMediaPlayer.EndOfMedia is triggered but not exported in PySide6 as enum; use state checks if needed
        if st == QMediaPlayer.MediaStatus.EndOfMedia:
            self.playbackFinished.emit()
