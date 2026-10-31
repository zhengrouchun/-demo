"""Device enumeration runs in a disposable process, too."""
if __name__ == "__main__":
    import json
    from ..audio.devices import enumerate_audio_devices
    print(json.dumps(enumerate_audio_devices(), ensure_ascii=True))
