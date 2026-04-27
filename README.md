# 🌌 BRING Project

<p align="center">
  <img src="assets/poster.png" alt="BRING Project Poster" width="600"/>
</p>

> **B**ackground AI | **R**emembrance | **I**nteractive | **N**arrative | **G**raph

**BRING** is an advanced, multi-agent framework designed to revolutionize AI-driven role-playing and interactive storytelling. Our mission is to move beyond static chatbots and create a living, breathing, and unpredictable world where AI doesn't just converse with you—it directs, challenges, and immerses you in a deep narrative.

---

## 🛑 The Core Problem (Flaws in Current LLMs)
Current AI models suffer from two major structural weaknesses when it comes to role-playing and world-building:

1. **Context Degradation & Hallucination:** 
   As conversations grow longer, the AI tends to forget the established rules of the world. It hallucinates facts and ultimately breaks the narrative structure, relying only on the user's most recent prompts.
2. **Passive Storytelling & The "People-Pleasing" Flaw:** 
   Current models are purely reactive. They converse but fail to drive the plot forward. No unexpected events (e.g., sudden family crises, villain attacks, or natural disasters) occur outside the user's direct command. The AI constantly tries to "please" the user, which entirely eliminates tension, challenge, and realism.

---

## 💡 Our Solution: A Living, Graph-Driven Ecosystem
The core philosophy of **BRING** is the implementation of a robust, invisible background framework. Instead of relying on a single AI, we use a synergistic multi-agent system that enforces world logic, generates random events, simulates antagonists, and creates genuine challenges. The user will feel like they are interacting within a living society, not just talking to a machine.

To manage the massive scale of world-building data (such as lore extracted from light novels), information is not stored linearly. Instead, **BRING** utilizes a **Graph-based and Clustered Memory System**. This allows the framework to efficiently manage complex lore and organically inject only the relevant pieces into the narrative exactly when needed.

---

## 🧠 System Architecture (The Tri-Layer Design)
BRING is powered by three distinct LLM agents, each with strictly defined responsibilities, working in unison to craft a flawless narrative:

### 🎭 Layer 1: The Actor (Frontend UI / Interaction LLM)
This is the frontline agent that interacts directly with the user.
* **Role:** Executes the story, role-plays characters, and manages natural, engaging dialogue.
* **Focus:** Tone, expression, and flawless real-time character impersonation.

### 🎬 Layer 2: The Director & Antagonist (Background Orchestrator LLM)
The mastermind operating behind the scenes. It oversees Layer 1.
* **Role:** Maintains the overarching narrative structure, enforces world rules, and steers the plot.
* **Special Feature:** This layer actively plays the role of the **Antagonist**. It controls background NPCs, generates sudden plot twists, directs villains, and actively throws the protagonist (the user) into challenging situations to keep the story thrilling.

### ⏳ Layer 3: The Chronicler (Timeline & Memory LLM)
A vital agent dedicated to preventing chronological chaos in long-term memory.
* **Role:** Meticulously logs major events and maintains a strict chronological Timeline.
* **Focus:** Prevents temporal paradoxes (e.g., ensuring an event from 10 years ago isn't confused with something that happened last week) and guarantees the narrative's historical consistency.

---

## 🛠 Technical Status & Architecture
The project is being developed with a strict adherence to **Clean Code** principles and a highly **modular** design.

* **Current Status:** Work in Progress (WIP) 🚧
* **Tech Stack & Foundation:**
  * **`any-llm`**: Utilized for seamless integration with multiple LLM providers.
  * **`Instructor`**: Implemented to guarantee strict, reliable Structured Outputs from the models.
  * **Asynchronous Design**: Built completely `Async` to prevent latency bottlenecks during inter-agent communication.
  * **`llm_gateway`**: A unified, highly modular gateway has already been successfully developed and integrated.

---

## 🤝 Contributing
We are always open to new ideas, feedback, and contributions from the community! The development of further modules (including the Graph system and the Director's logic) is actively underway.

*Built with ❤️ to elevate the paradigm of AI storytelling.*
