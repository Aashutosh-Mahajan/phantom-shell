# Software and model licenses

## PHANTOM SHELL

PHANTOM SHELL is distributed under the MIT License; see [LICENSE](LICENSE). This application license is separate from the model and third-party licenses below.

## Runtime and Python dependencies

- [psutil](https://github.com/giampaolo/psutil/blob/master/LICENSE) — BSD 3-Clause.
- [Rich](https://github.com/Textualize/rich/blob/main/LICENSE) — MIT.
- [Ollama](https://github.com/ollama/ollama/blob/main/LICENSE) — MIT. Ollama is installed separately and is not included in this Python package.

Review and retain the full license texts and notices when packaging or redistributing those components. Transitive dependency licenses should be generated from the final resolved environment before shipping a binary distribution.

## Model

The configured Gemma model (verified here with `gemma4:e4b`) is governed by the [Gemma Terms of Use](https://ai.google.dev/gemma/terms), not by the PHANTOM SHELL application license. Check the terms for the exact model version and intended use. The model's availability in Ollama does not make the weights an OSI-licensed software dependency.
