# Running costs: OpenAI API and local image generation

Prices checked **October 19, 2026**, in **USD**. Estimates below exclude taxes,
hosting and storage. Check the linked provider prices before a larger run.

You can explore the catalog, inspect evidence and present saved portraits without
making a paid AI call. The current **Generate image** button uses OpenAI; a local
image-generation backend is **not yet integrated**.

## What costs money today?

| Activity | AI API charges | Other costs |
| --- | --- | --- |
| Browse the bundled catalog and saved portraits | None | Running the app, storage and any hosting |
| Build a catalog prompt or run deterministic FITS analysis | None | CPU, memory, downloads and storage |
| Generate a new portrait in WebbWatch | Metered OpenAI image API usage | App hosting and saved image storage |
| Generate an image in an external local workflow | No API fee when inference runs entirely locally | Hardware, electricity, model downloads and setup time |
| Optional AI review of a JWST analysis report | Separate text/vision model usage, or local inference | Depends on the selected report provider |

The Ollama/llama.cpp report integration does not generate portraits. Selecting a
local report model does not change the portrait provider.

## OpenAI: the implemented portrait workflow

The default model is `gpt-image-2.5-sunburst`, configured by `PORTRAIT_IMAGE_MODEL`.
Each request asks for **one 1024×1024, medium-quality PNG**. The app sends a text
prompt through the Images API; it does not currently send an input image.

Current standard token rates for that model:

| Token type | Price per 1 million tokens |
| --- | ---: |
| Text input | $5.00 |
| Image input, if an editing workflow is added | $8.00 |
| Image output | $30.00 |

Source: [OpenAI's model pricing](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst).
These are token rates, not a fixed price per picture. Different prompts, outputs,
models or quality settings can change the bill.

### Our recorded test

The [completed LTT 9779 b test](HANDOFF.md#19-generate-and-retain-a-planet-portrait-in-webbwatch-2026-10-19)
reported **1,973 text input tokens** and **439 image output tokens**:

```text
Estimated cost = (1,973 × $5 + 439 × $30) / 1,000,000
               = $0.023035, or about 2.3 cents
```

That is a calculation from recorded usage, not an invoice or a guaranteed cost
for the next image. The saved generation ID is
`aa47fc61-67dc-415a-adf7-4061eea1dd3a`.

| Number of generations | Estimate if each used the same tokens |
| ---: | ---: |
| 1 | $0.023 |
| 10 | $0.23 |
| 100 | $2.30 |
| 1,000 | $23.04 |

Count every attempted version when budgeting. For example, two successful versions
per planet would double these estimates. A timeout or a failure saving an image
does not prove that the provider did no billable work.

The app admits one active generation, deduplicates repeated request IDs and disables
automatic API retries. It records returned usage with the saved evidence. These
controls reduce duplicate requests; there is **no app-enforced dollar spending cap**.
`PORTRAIT_GENERATION_ENABLE=false` disables new portrait generation after an API
restart; it does not cancel an already submitted request. Cloud report settings are
separate. See the [generation setup](../README.md#generate-and-save-a-portrait-in-webbwatch)
and [OpenAI Images API guide](https://developers.openai.com/api/docs/guides/image-generation).

## Local generation: no API fee, but real operating costs

One available example is **FLUX.1 [schnell]**, whose publisher provides Apache 2.0
weights and instructions for local ComfyUI and Diffusers workflows. See the
[official model card and license](https://huggingface.co/black-forest-labs/FLUX.1-schnell).
Check the exact model and accompanying components' terms; a freely downloadable
model is not automatically covered by WebbWatch's MIT license.

For now, local generation is a manual experiment: export/copy the planet's prompt
and evidence, run a locally configured image workflow, and retain its output beside
the source brief. Record the model revision, seed, resolution, steps and any prompt
edits. Those images are not automatically imported into WebbWatch's saved portraits.
Check the model's prompt-length limits: a long WebbWatch brief may need a reviewed
adaptation, and silent truncation can lose scientific constraints.

We have **not benchmarked local image generation on this project's RTX 3070
(8 GB VRAM)**. The existing local text-report benchmark does not establish image
speed or memory requirements. Model size, precision, CPU offloading, resolution and
sampling steps all affect the result. Measure on the actual machine before buying
hardware or projecting throughput.

Electricity is straightforward to estimate from measured wall power:

```text
Electricity per image = (watts / 1,000) × (seconds / 3,600) × price per kWh

Illustrative assumptions only:
450 W × 60 seconds at $0.20/kWh = $0.0015 per image
                              = $1.50 per 1,000 images
```

The 60-second runtime and 450 W draw are **not benchmark results**. This excludes
idle time, hardware purchase/depreciation, storage and your time. If a hypothetical
$600 hardware purchase were allocated across 10,000 images, hardware alone would
add $0.06 per image. Existing hardware can make a small experiment inexpensive;
buying a GPU solely to avoid a few dollars in API charges needs a measured comparison.

## A small comparison before scaling up

Start with the existing saved images for a demonstration. To evaluate a local
generator, choose three representative planets, preserve their original evidence,
and generate one local image per target. Compare against existing cloud examples
where available; record any differences in prompt or settings.

Measure elapsed time, peak memory, wall energy if available, and how many attempts
produce an acceptable illustration. Compare **cost per accepted image**, including
rejected attempts and review time. Neither cloud nor local generation validates
the depicted geometry, color or atmosphere. The Measured / Inferred / Illustrative
distinction still applies.

These image estimates also exclude archive ingestion, FITS processing, database
hosting, backups, storage and network egress. Public input data does not make an
exabyte-scale pipeline free. The current tests establish small local workloads;
exabyte operation remains an architecture target.
