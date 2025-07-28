from utils.config import RetrieveConfig
from utils.llm import LLM
from utils.prompts import (
  GENERATE_RETRIEVAL_QUERY_SYSTEM_INPUT, 
  GENERATE_RETRIEVAL_QUERY_USER_INPUT, 
  JUDGE_USEFUL_FUNCTIONS_SYSTEM_INPUT, 
  JUDGE_USEFUL_FUNCTIONS_USER_INPUT
)
import requests

class Retriever:

    def __init__(self, config: RetrieveConfig, llms: dict[str, LLM] = None):
        self.config = config
        self.llms = llms
        if not config.use_llm_optimize:
          self.config.optimize_model_name = "NO_OPTIMIZE" 

    def _optimize_queries(self, queries: list[str], llm: LLM):
        system_inputs = [GENERATE_RETRIEVAL_QUERY_SYSTEM_INPUT] * len(queries)
        user_inputs = [GENERATE_RETRIEVAL_QUERY_USER_INPUT.format(question_input=query) for query in queries]
        prompts = llm.apply_chat_template(system_inputs, user_inputs)
        results = llm.batch_generate(prompts)
        return [result["output"] for result in results]
    
    def _extract_functions(self, question_inputs: list[str], function_inputs: list[list[str]], llm: LLM):
        system_inputs = [JUDGE_USEFUL_FUNCTIONS_SYSTEM_INPUT] * len(question_inputs)
        user_inputs = [
            JUDGE_USEFUL_FUNCTIONS_USER_INPUT.format(question_input=question_input, function_input=function_input) 
            for question_input, function_input in zip(question_inputs, function_inputs)
        ]
        prompts = llm.apply_chat_template(system_inputs, user_inputs)
        results = llm.batch_generate(prompts)
        useful_functions = []
        top_k = self.config.top_k
        for result, function_input in zip(results, function_inputs):
            judgments = result["output"][1:-1].split(',')
            useful_function = [function_input[index] for index, judgment in enumerate(judgments) if judgment.strip() == 'USEFUL' and index < top_k]
            if len(useful_function) > 3:
                useful_function = useful_function[:3]
            useful_functions.append(useful_function)
        
        return useful_functions
    
    def _retrieve_functions(self, queries: list[str]):
        retrieved_functions = []
        for query in queries:
            response = requests.post(
                self.config.url,
                json={"query": query, "top_k": self.config.top_k, "model": self.config.retriever_model},
            )
            response = response.json()
            retrieved_functions.append([doc['function'] for doc in response[0]['retrieved_documents']])
        return retrieved_functions

    def retrieve(self, queries, optimize_llm: LLM = None):
        if optimize_llm is None and self.config.use_llm_optimize:
            if self.llms is None:
                raise ValueError("Optimizer LLM is not set")
            optimize_llm = self.llms[self.config.optimize_model_name]

        if self.config.use_llm_optimize:
            queries = self._optimize_queries(queries, optimize_llm)
        functions = self._retrieve_functions(queries)
        if self.config.extract_functions:
            functions = self._extract_functions(queries, functions, optimize_llm)
        return functions