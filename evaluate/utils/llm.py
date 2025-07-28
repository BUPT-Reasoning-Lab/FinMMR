from utils.config import LLMConfig
from tqdm.asyncio import tqdm_asyncio
import asyncio
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic 
import aiolimiter
from loguru import logger

class LLM:

    def __init__(self, config: LLMConfig):
        self.config = config
        if config.api_style == 'openai':
            self.client = AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)    
        elif config.api_style == 'claude':
            self.client = AsyncAnthropic(api_key=config.api_key)
        else:
            raise ValueError(f"Invalid API style: {config.api_style}")
        self.limiter = aiolimiter.AsyncLimiter(1, 60 / config.rpm)
    
    def __getattr__(self, name):
        if hasattr(self.config, name):
            return getattr(self.config, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def apply_chat_template(self, system_inputs: list[str], user_inputs: list[str]):
        prompts = []
        for system_input, user_input in zip(system_inputs, user_inputs):
            if self.config.support_system_role:
                messages = [{"role": "system", "content": system_input}, {"role": "user", "content": user_input} ]
            else:
                messages = [ {"role": "user", "content": system_input + "\n" + user_input}]
            prompts.append(messages)
        return prompts
    
    def _format_openai_response(self, response):
        if response:
            response = response.model_dump()
            content = response["choices"][0]["message"]["content"]
            completion_tokens = response["usage"]["completion_tokens"]
            reasoning_content = response["choices"][0]["message"].get("reasoning_content", None)
            return { "output": content, "reasoning_content": reasoning_content, "completion_tokens": completion_tokens, "raw_response": response }
        else: return { "output": None, "reasoning_content": None, "completion_tokens": None, "raw_response": None }
    
    def _format_claude_response(self, response):
        if response:
            response = response.model_dump()
            content = response["content"][0]['text']
            completion_tokens = response["usage"]["output_tokens"]
            return { "output": content, "reasoning_content": None, "completion_tokens": completion_tokens, "raw_response": response }
        else: return { "output": None, "reasoning_content": None, "completion_tokens": None, "raw_response": None }
    

    async def _async_claude_generate(self, prompt: list[dict]):
        response = await self.client.messages.create(
            model=self.config.model_id,
            messages=prompt,
            **self.config.sampling_args,
        )
        return self._format_claude_response(response)

    async def _async_openai_generate(self, prompt: list[dict]):
        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=prompt,
            **self.config.sampling_args,
        )
        return self._format_openai_response(response)

    @property
    def _async_generate(self):
        if self.config.api_style == 'openai':
            return self._async_openai_generate
        elif self.config.api_style == 'claude':
            return self._async_claude_generate
    
    async def _async_generate_with_limiter(self, prompt: list[dict]):
        async with self.limiter:
            for i in range(self.config.max_retries):
                try:
                    return await self._async_generate(prompt)
                except Exception as e:
                    logger.error(f"Error generating response: {e} current retry {i + 1} of {self.config.max_retries}")
                    continue
        logger.error(f"Failed to generate response after {self.config.max_retries} retries")
        return self._format_openai_response(None)
    
    async def async_generate(self, prompt: list[dict]):
        return await self._async_generate_with_limiter(prompt)
    
    async def async_batch_generate(self, prompts: list[list[dict]], desc: str = "Generating"):
        async_responses = [ self.async_generate(prompt) for prompt in prompts ]
        responses = await tqdm_asyncio.gather(*async_responses, desc=desc)
        return responses

    def batch_generate(self, prompts: list[list[dict]], desc: str = "Generating"):
        return asyncio.run(self.async_batch_generate(prompts, desc))

