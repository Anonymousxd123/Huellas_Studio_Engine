"""Minimal utility nodes required by the Huellas LTX-Video 0.9.6 workflow.

These two nodes intentionally replace a dependency on the much larger
ComfyUI-KJNodes package. They are installed into the user's ComfyUI tree by
scripts/setup_ltx_animation_macos.sh.
"""


class StringToFloatList:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string": ("STRING", {"default": "1.0, 0.5, 0.0", "multiline": True})
            }
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("FLOAT",)
    CATEGORY = "Huellas/Animation"
    FUNCTION = "create_list"

    def create_list(self, string):
        try:
            values = [float(value.strip()) for value in string.split(",")]
        except (TypeError, ValueError) as exc:
            raise ValueError("La lista de sigmas debe contener números separados por comas") from exc
        if len(values) < 2:
            raise ValueError("La lista de sigmas necesita al menos dos valores")
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("Los sigmas deben estar entre 0 y 1")
        if any(values[index] < values[index + 1] for index in range(len(values) - 1)):
            raise ValueError("Los sigmas deben estar en orden descendente")
        return (values,)


class FloatToSigmas:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "float_list": ("FLOAT", {"forceInput": True})
            }
        }

    RETURN_TYPES = ("SIGMAS",)
    RETURN_NAMES = ("SIGMAS",)
    CATEGORY = "Huellas/Animation"
    FUNCTION = "to_sigmas"

    def to_sigmas(self, float_list):
        import torch

        values = [float(value) for value in float_list]
        if len(values) < 2:
            raise ValueError("Se requieren al menos dos sigmas")
        if any(values[index] < values[index + 1] for index in range(len(values) - 1)):
            raise ValueError("Los sigmas deben estar en orden descendente")
        return (torch.tensor(values, dtype=torch.float32),)


NODE_CLASS_MAPPINGS = {
    "StringToFloatList": StringToFloatList,
    "FloatToSigmas": FloatToSigmas,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StringToFloatList": "String to Float List (Huellas)",
    "FloatToSigmas": "Float to Sigmas (Huellas)",
}
