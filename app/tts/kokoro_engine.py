from pathlib import Path
import soundfile as sf
import numpy as np

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

    def synth_sentences(self, sentences, out_dir: Path, on_progress=None):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        filtered = [s.strip() for s in sentences if s and s.strip()]
        total = len(filtered)
        text = "\n".join(filtered)
        gen = self.pipeline(text, voice=self.voice, speed=self.speed, split_pattern=r"\n+")
        paths = []
        for idx, (gs, _ps, audio) in enumerate(gen):
            path = out_dir / f"{idx:05d}.wav"
            sf.write(path.as_posix(), audio, self.sr)
            paths.append((idx, gs, path.as_posix(), len(audio)/self.sr))
            if on_progress:
                try:
                    on_progress(idx + 1, total)
                except Exception:
                    pass
        return paths

    def synth_chunks(self, texts, out_dir: Path, on_progress=None):
        """texts: list[str]; returns (records, merged_path, sr)
        records[i] = (path, duration_sec)
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        total = len(texts)
        text = "\n".join(t.strip() for t in texts)
        gen = self.pipeline(text, voice=self.voice, speed=self.speed, split_pattern=r"\n+")
        paths = []
        audios = []
        for idx, (gs, _ps, audio) in enumerate(gen):
            path = out_dir / f"{idx:05d}.wav"
            sf.write(path.as_posix(), audio, self.sr)
            paths.append((idx, gs, path.as_posix(), len(audio)/self.sr))
            audios.append(np.asarray(audio, dtype=np.float32))
            if on_progress:
                try:
                    on_progress(idx + 1, total)
                except Exception:
                    pass
        # merge
        if audios:
            merged = np.concatenate(audios)
        else:
            merged = np.zeros((0,), dtype=np.float32)
        merged_path = out_dir / "merged.wav"
        sf.write(merged_path.as_posix(), merged, self.sr)
        # compute offsets
        offsets = []
        cursor = 0
        for idx, a in enumerate(audios):
            start_ms = int(cursor * 1000 / self.sr)
            dur_ms = int(len(a) * 1000 / self.sr)
            end_ms = start_ms + dur_ms
            cursor += len(a)
            offsets.append((start_ms, end_ms))
        return paths, merged_path.as_posix(), self.sr, offsets
