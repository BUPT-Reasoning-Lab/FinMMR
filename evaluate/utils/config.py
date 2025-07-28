from typing import Optional, Literal
from pydantic import BaseModel, field_validator, computed_field
from .prompts import MODEL_PROMPT_DICT
import yaml
import os


class PromptConfig(BaseModel):
    prompt_type: str

    @field_validator("prompt_type")
    def validate_prompt_type(cls, v):
        if v not in MODEL_PROMPT_DICT.keys():
            raise ValueError(f"Invalid prompt type: {v}")
        return v

    @computed_field(return_type=str)
    def template(self):
        return MODEL_PROMPT_DICT[self.prompt_type]


class LLMConfig(BaseModel):
    model_id: str
    support_system_role: bool 
    reasoner: bool 
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    sampling_args: dict = {}
    max_retries: int = 3
    api_style: Literal['openai', 'claude'] = 'openai'
    rpm: int = 60  # requests per minute

class RetrieveConfig(BaseModel):

    url: str
    top_k: int = 30
    use_llm_optimize: bool = False
    retriever_model: str = "contriever-msmarco"
    extract_functions: bool = False
    optimize_model_name: Optional[str] = None


class InferenceConfig(BaseModel):
    model_name: str
    llms: dict[str, LLMConfig]
    data_dir: str = "./data"
    output_dir: str = "./results"
    dataset: str
    subset: str
    prompt: PromptConfig
    use_retrieve: bool = False
    retrieve: Optional[RetrieveConfig] = None

    @classmethod
    def from_yaml(cls, yaml_path: str):
        with open(yaml_path, "r") as f:
            config_dict = yaml.safe_load(f)
        llms = {}
        for key, value in config_dict["llms"].items():
            llms[key] = LLMConfig(**value)
        config_dict['inference']['llms'] = llms
        config = cls(**config_dict["inference"])
        return config

    @computed_field(return_type=str)
    def save_path(self):
        return os.path.join(
            self.output_dir,
            self.dataset,
            self.subset,
            self.prompt.prompt_type,
            self.model_name,
        )
    
    @computed_field(return_type=str)
    def data_file(self):
        return os.path.join(
            self.data_dir,
            self.dataset,
            f"{self.subset}.json",
        )
    
class EvaluationConfig(BaseModel):
    result_dir: str = './results'
    model_name: str
    dataset: str
    subset: str
    ans_extract_model_name: str
    force_extract_answer: bool = False 
    prompt_type: str
    llms: dict[str, LLMConfig]
    timeout_duration: int = 10 # For POT

    @classmethod
    def from_yaml(cls, yaml_path: str):
        with open(yaml_path, "r") as f:
            config_dict = yaml.safe_load(f)
        llms = {}
        for key, value in config_dict["llms"].items():
            llms[key] = LLMConfig(**value)
        config_dict["evaluation"]["llms"] = llms
        config = cls(**config_dict["evaluation"])
        return config

    @field_validator("prompt_type")
    def validate_prompt_type(cls, v):
        if v not in MODEL_PROMPT_DICT.keys():
            raise ValueError(f"Invalid prompt type: {v}")
        return v
    
    @computed_field(return_type=str)
    def save_path(self):
        return os.path.join(
            self.result_dir,
            self.dataset,
            self.subset,
            self.prompt_type,
            self.model_name,
        )

    @computed_field(return_type=str)
    def evaluation_file(self):
        return os.path.join(
            self.save_path,
            "evaluation.json",
        )

    @computed_field(return_type=str)
    def inference_file(self):
        return os.path.join(
            self.save_path,
            "inference.json",
        )
    
    
