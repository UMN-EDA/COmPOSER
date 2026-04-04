# Serialized Model Storage

This directory contains the serialized trained models used throughout the RF design automation flow.

Models are stored in `.pkl` format to support fast loading during iterative design optimization and layout generation. This avoids repeated retraining, reduces runtime overhead, and ensures that the same trained model can be reused consistently across multiple workflow stages.

The `.pkl` format is particularly suitable here because it preserves the complete trained model object, including learned parameters and any attached preprocessing or pipeline configuration, in a form that can be reloaded directly by the corresponding Python scripts.

> **Repository Note**
> The actual model files are not committed to the repository because of repository size limitations.

Instead, these models are generated automatically during training of their corresponding workflows and can be recreated locally by running the appropriate training scripts. After training, the generated model files are stored in this directory for subsequent reuse.

