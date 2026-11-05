# Roadmap

The current focus is to finish English-primary V1 on Ubuntu with GNOME.
The application ships as alpha source. The [command guide](commands/USER_COMMAND_GUIDE.md)
covers implemented paths and prerequisites. The [validation guide](VALIDATION.md)
describes the evidence for those paths.

| Area | Current status | Open work |
| --- | --- | --- |
| Speech and command handling | Replaceable local recognition, standby, bounded rules and optional local model proposals | Measure English recognition and end-to-end target accuracy, first-wake behavior and resource use with versioned corpora |
| Desktop control | Permission-gated actions with fresh target evidence and explicit outcome reporting | Extend application and layout acceptance for window picking, app-scoped close, Ptyxis tabs, capture and Telegram navigation |
| Remembered consent | Input-session restoration and revocation covered by deterministic tests | Validate restoration across a real OS restart and across supported portal configurations |
| Feedback and languages | Separate UI, command, speech-output and status languages; limited experimental Persian command compatibility | Validate live caption delivery, voice routing and recognition per language |
| Installation and portability | Python source setup and GNOME Shell 50 integration | Improve model and runtime setup and evaluate additional desktop adapters |

The roadmap gives the direction of work. The [release policy](RELEASE_POLICY.md)
describes how public milestones are published.
