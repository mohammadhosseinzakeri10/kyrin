import sounddevice as sd


def check_sample_rate(device: int, rate: int) -> bool:
    """Check whether a device supports the given input sample rate."""
    try:
        sd.check_input_settings(
            device=device,
            channels=1,
            dtype="int16",
            samplerate=rate,
        )
    except sd.PortAudioError:
        return False

    return True


sample_rates = (16000, 32000, 44100, 48000)
devices = (4, 5)

for device in devices:
    print(f"\nDevice {device}:")

    for rate in sample_rates:
        if check_sample_rate(device, rate):
            print(f"  {rate} Hz: supported")
        else:
            print(f"  {rate} Hz: not supported")
