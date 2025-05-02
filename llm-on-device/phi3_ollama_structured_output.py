from pydantic import BaseModel, Field  # ✅ Use standard pydantic v2
from langchain_core.prompts import PromptTemplate
from langchain_experimental.llms.ollama_functions import OllamaFunctions
from langchain_community.chat_models import ChatOllama

# Define schema
class Person(BaseModel):
    name: str = Field(description="The person's name")
    height: float = Field(description="The person's height")
    hair_color: str = Field(description="The person's hair color")

# Input context
context = """Alex is 5 feet tall. 
Claudia is 1 foot taller than Alex and jumps higher than him. 
Claudia is a brunette and Alex is blonde."""

# Prompt
prompt = PromptTemplate.from_template(
    """<|user|>{context}

QUESTION: {question}<|end|>
<|assistant|>AI: """
)

# Chain
llm = OllamaFunctions(
    model="phi4-mini",
    format="json",
    temperature=0
)

# Structured output
structured_llm = llm.with_structured_output(Person)
chain = prompt | structured_llm

# Run
response = chain.invoke({
    "question": "Who is shorter?",
    "context": context
})

print(response)
