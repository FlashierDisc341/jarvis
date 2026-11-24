"""No GPU/model/microphone/app actions. Tests endpoint timing, wake parsing and resampling."""
import unittest

import av
import numpy as np

from jarvis_whisper_audio import SpeechGate
from jarvis_whisper import remove_wake_marker


class SpeechGateTests(unittest.TestCase):
    def test_silence_does_not_start_recording(self):
        gate = SpeechGate()
        for _ in range(30):
            self.assertEqual(gate.feed(0.05, 0.15), "waiting")
        self.assertFalse(gate.active)

    def test_phrase_ends_after_pause(self):
        gate = SpeechGate()
        self.assertEqual(gate.feed(0.8, 0.2), "start")
        self.assertEqual(gate.feed(0.7, 0.2), "continue")
        for _ in range(3):
            self.assertEqual(gate.feed(0.05, 0.2), "continue")
        self.assertEqual(gate.feed(0.05, 0.2), "complete")

    def test_brief_pause_does_not_split(self):
        gate = SpeechGate()
        gate.feed(0.9, 0.2)
        self.assertEqual(gate.feed(0.05, 0.3), "continue")
        self.assertEqual(gate.feed(0.8, 0.2), "continue")
        self.assertEqual(gate.silence, 0)

    def test_overlong_audio_discarded(self):
        gate = SpeechGate(max_seconds=1)
        gate.feed(0.8, 0.2)
        self.assertEqual(gate.feed(0.8, 0.9), "discard")

    def test_invalid_probability_discarded(self):
        self.assertEqual(SpeechGate().feed(float("nan"), 0.2), "discard")


class WakeTests(unittest.TestCase):
    def test_real_test_transcripts(self):
        for transcript, expected in (
            ("Jarvis, what is the volume?", "what is the volume"),
            ("Set volume to 30% Jarvis.", "set volume to 30%"),
            ("Jarvis, volume down.", "volume down"),
            ("What day of the week is it, Jarvis?", "what day of the week is it"),
            ("Jarvis.", ""),
        ):
            self.assertEqual(remove_wake_marker(transcript), expected)

    def test_require_boundary(self):
        self.assertIsNone(remove_wake_marker("what time is it"))
        self.assertIsNone(remove_wake_marker("we told jarvis about the time"))
        self.assertIsNone(remove_wake_marker("jarvisian what time is it"))
        self.assertEqual(remove_wake_marker("jarvis open jarvis"), "open jarvis")


class ResamplerTests(unittest.TestCase):
    def test_native_audio_to_whisper_format(self):
        for rate in (44100, 48000, 16000):
            samples = rate // 10
            source = np.zeros((1, samples), dtype=np.int16)
            frame = av.AudioFrame.from_ndarray(source, format="s16", layout="mono")
            frame.sample_rate = rate
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            output = list(resampler.resample(frame)) + list(resampler.resample(None))
            audio = np.concatenate([item.to_ndarray().reshape(-1) for item in output])
            self.assertEqual(audio.dtype, np.float32)
            self.assertEqual(len(audio), 1600)


if __name__ == "__main__":
    unittest.main()
