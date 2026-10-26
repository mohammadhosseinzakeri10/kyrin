import sounddevice as sd  # type: ignore[import-untyped]

device = 4
sample_rate = 48000
channels = 1
dtype = "int16"
frames = 1024


with sd.RawInputStream(
    device=device,
    samplerate=sample_rate,
    channels=channels,
    dtype=dtype,
) as stream:
    print("Microphone stream started.")

    data, overflowed = stream.read(frames)

    print(f"Received {len(data)} bytes.")
    print(f"Overflowed: {overflowed}")
