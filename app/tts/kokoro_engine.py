from pathlib import Path
import soundfile as sf

class KokoroNotAvailable(Exception):
    pass

class KokoroTTS:
    def __init__(self, lang_code='a', voice='af_heart', speed=1.0, sr=24000):
        # Lazy-import so the UI can run without Kokoro until generation time.
        try:
            from kokoro import KPipeline  # type: ignore
        except Exception as e:
            raise KokoroNotAvailable("Kokoro not installed or failed to import. Install with: pip install kokoro") from e
        self._KPipeline = KPipeline
        self.pipeline = self._KPipeline(lang_code=lang_code)
        self.voice, self.speed, self.sr = voice, speed, sr

    def synth_sentences(self, sentences, out_dir: Path):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        text = "\\n".join(s.strip() for s in sentences if s.strip())
        gen = self.pipeline(text, voice=self.voice, speed=self.speed, split_pattern=r"\\n+")
        paths = []
        for idx, (gs, _ps, audio) in enumerate(gen):
            path = out_dir / f"{idx:05d}.wav"
            sf.write(path.as_posix(), audio, self.sr)
            paths.append((idx, gs, path.as_posix(), len(audio)/self.sr))
        return paths
