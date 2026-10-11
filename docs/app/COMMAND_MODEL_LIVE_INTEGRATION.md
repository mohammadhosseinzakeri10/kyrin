# Local command models in the Ubuntu application

The **Command Understanding** page can select an installed model from a local
Ollama model store. The initial selection is **Fast rules only**, preserving
the existing behavior until the owner chooses a model. Four development tags
are currently present in the Git-ignored store at
`models/local/command-understanding/ollama/`; model weights are never copied
into application settings or Git.

## Use

1. Open KYRIN and go to **Command Understanding**.
2. Select **Ollama**, confirm the local model-store directory, and click
   **Refresh installed models**.
3. Choose a model and **Auto**, **CPU**, or **GPU**. CPU and GPU use the same
   model files; the Ollama runner chooses where to compute. An explicit GPU
   request fails if inference did not use GPU memory. Auto lets Ollama decide.
4. Click **Save**. KYRIN stops and restarts the listening session with the new
   selection. Use **Speech Recognition → Diagnostics** to inspect recognized
   speech and interpreted commands. Desktop actions still need the separate
   permissions in **Actions**.

KYRIN starts a private loopback Ollama server with the selected store for the
listening session. It does not alter the user's default Ollama daemon, download
models, or use a cloud service. The server stops with that session. Missing or
incomplete models cause a visible start error rather than a silent switch.

## Decision boundary

The model proposes command meaning only. Existing fast rules decide simple
commands immediately; unresolved final transcripts are sent to the model.
Model output cannot directly execute anything. The original transcript must
independently support the proposed operation and target, the target must resolve
to exactly one installed and permitted application, and the normal action gate
must approve it. Negation, uncertainty, unsupported operations, model errors,
and unverified targets never turn into an action. Existing two-step power
confirmation remains separate.

This is a usable local integration, not a claim of general multilingual
understanding. The independent source checks currently cover English and
Persian. Other languages need reviewed source-language evidence before model
proposals can execute. CPU inference may pause command handling while the model
runs; follow-up responsiveness and real microphone behavior require owner
validation. Model quality and false-rejection rates must be measured with the
existing verified speech corpus before choosing a default model.
