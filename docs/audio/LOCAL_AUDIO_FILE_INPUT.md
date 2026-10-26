# Local audio-file input

The control window has a small import target immediately below its status bar.
It accepts one local `.wav`, `.mp3`, `.m4a`, or `.ogg` file by drag and drop, clipboard
paste, or file chooser. The optional GNOME character has a **Paste audio**
button, which asks the running control window to paste the currently copied
file. The character itself is a GNOME Shell actor; Shell's external drag API
does not expose dropped Nautilus file contents to this extension. Dragging a
file directly onto that actor is therefore not advertised as working. The
control-window target is the supported drag destination.

`AudioFileInput` decodes a local file through the already installed `ffmpeg`
executable into mono 16-bit PCM at 16 kHz. It streams chunks without copying
the original or writing a decoded temporary file. `UbuntuSessionFactory`
uses the same VAD, selected STT engine, interpreter, action gate, and feedback
route as live microphone input. The application stops the microphone session
before file processing and restores its prior listening state afterward.
Imported speech is interpreted immediately; there is no file-specific approval
step. Existing action permissions apply. Controls with sensitive or unknown
consequences remain blocked until a separate confirmation flow exists.

Only one file can be processed at a time. An import is rejected if no STT
model is selected, the file is not local, the suffix is unsupported, the file
exceeds 512 MiB, or `ffmpeg` is missing. Files use a finite, ordered VAD/STT
pipeline without the microphone's real-time queue or playback delay. Total
time depends on decoding and the selected STT model, and can be shorter than
the file's duration. The microphone is still stopped before import so the two
sessions cannot load competing models into GPU memory.
File command submission waits for both understanding-queue and action-queue
capacity. Natural EOF preserves accepted finals: understanding drains before
the action queue, with a separate 60-second limit for each worker. Explicit
user cancellation wakes capacity waits, discards queued understanding/actions,
and invalidates in-flight understanding results. Understanding has a one-second
stop/join budget; timeout is an error, not proof the model thread stopped.
An action already running is not rolled back.
For Whisper file sessions, provisional previews are disabled: the model
transcribes each completed speech turn once instead of reprocessing intermediate
previews. Microphone sessions retain their live preview behavior.

The GNOME Shell change requires a fresh desktop session before the character's
new button appears. The Qt control-window import target requires restarting
the KYRIN application process. No model download is needed for this feature.
