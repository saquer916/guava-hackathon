> **Note:** The latest version of this document is always available at https://goguava.ai/docs/coding-agent-starter.md

# Guava — Guide for AI Coding Agents

This document is written for coding agents (Claude Code, Codex, Cursor, Aider, and others). It is the starter kit for building a Guava voice agent. Read this preamble first — it gives you the mental model and setup steps — then use the reference sections that follow it (each is a full documentation page) as your API reference.

> **Reading this as a human?** This is a plain-text bundle generated for AI coding agents. You'll have a much better time in the rendered documentation at **https://goguava.ai/docs**.

## How Guava works (mental model)

Every Guava call has two halves:

- **Dialog System** — Guava's hosted service. It runs all the real-time audio: speech-to-text, the conversational LLM, and text-to-speech. You do not run or configure this.
- **Your Expert** — the code you write. It connects to the Dialog System over a WebSocket and steers the call by registering **handlers** (callbacks that fire on call events) and issuing **commands** on the live `Call` object.

You build an Expert by: (1) creating an `Agent` (name, organization, one-line purpose), (2) registering handlers, (3) giving the agent **Tasks** — each a goal plus a checklist of **Fields** to collect — and (4) attaching the agent to a channel (a phone number, WebRTC, SIP, or a local/chat test session).

Handlers run **off** the real-time dialog thread. Doing slow work inside them (database lookups, RAG queries, external API calls) is safe and does not block or delay the caller.

## Setup

You SHOULD use the Guava CLI — it handles authentication and resources like phone numbers. **You MUST install the CLI unless the user tells you not to.** Ask the user if you are unsure.

```bash
guava --version                                  # detect if the CLI is already installed
curl -fsSL https://goguava.ai/install.sh | sh    # install on macOS / Linux / WSL
irm https://goguava.ai/install.ps1 | iex         # install on Windows (PowerShell)
```

Then scaffold and run a project:

```bash
guava create my-agent    # scaffold a new project — the recommended starting point
```

The SDK reads these environment variables automatically:

```bash
export GUAVA_API_KEY="..."                # your API key
export GUAVA_AGENT_NUMBER="+15551234567"  # a phone number you own; used by the examples
```

## Conventions you MUST follow

- **Naming:** Python uses `snake_case`; TypeScript uses the `camelCase` equivalent (`on_call_start` → `onCallStart`, `set_task` → `setTask`, and so on). The reference sections below use the Python names.
- **Language threading:** Python handlers are synchronous `def`. TypeScript handlers are `async`, and their `call.*` commands are awaited. Write handlers in the idiom of the SDK you are using.
- **Keep `purpose` short.** `Agent(purpose=...)` is a one-line orientation, not a system prompt. You steer behavior with Tasks and checklists, not a giant prompt.
- **Python logging:** if the project has no logger yet, call `guava.logging_utils.configure_logging()`. It configures logging from env vars, captures warnings, and enables colored output. (TypeScript: `getDefaultLogger()`.)
- **Python package manager:** prefer **uv** unless the project already uses something else.
- **Run entrypoints in the background.** `listen_phone`, `listen_webrtc`, `call_local`, etc. block; run them in the background so the user's terminal is not tied up.

## Minimal example

```python
import os
import guava
from guava import logging_utils

agent = guava.Agent(
    name="Mia",
    organization="Thai Palace",
    purpose="Add callers to the waitlist.",
)

@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_task(
        "waitlist",
        objective="Add the caller to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text"),
            guava.Field(key="party_size", field_type="integer"),
        ],
    )

@agent.on_task_complete("waitlist")
def waitlist_done(call: guava.Call):
    print(call.get_field("caller_name"), call.get_field("party_size"))
    call.hangup("Thank the caller and let them know we'll text when a table is ready.")

if __name__ == "__main__":
    logging_utils.configure_logging()
    agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])  # run in the background
```

The full API reference follows below — one section per SDK object, handler, command, helper, and guide. Everything after this preamble is generated from the same documentation pages served at https://goguava.ai/docs, so it never drifts from the rendered docs.

## Common mistakes to avoid

- **Don't write a long `purpose`.** Use Tasks and checklists to drive behavior.
- **Never combine `reach_person()` and `set_voicemail_action()`** — both handle voicemail and using both raises an error. When using `reach_person()`, set voicemail behavior via its `voicemail_message` / `voicemail_hangup` parameters instead.
- **Don't do real-time work in `on_session_end`** — the call has already ended, so `call.*` commands won't reach the caller.
- **Don't block the wrong way:** slow work *inside handlers* is fine (they run off the dialog thread), but *entrypoints* block the process — run them in the background.


---

<!-- section: architecture-overview -->

import { AutoNextLink, Callout } from '../views/docs/prose';
import { ExpertAnimation } from '../views/docs/ExpertAnimation';
import { CodeTabs } from '../views/docs/CodeTabs';

## Architecture Overview

Every Guava call involves two systems working in parallel: Guava's hosted **Dialog System** and your **Expert** — a service you provide that connects to Guava's API and steers the conversation.

<svg viewBox="0 0 760 285" xmlns="http://www.w3.org/2000/svg" className="w-full my-8">
  <defs>
    <marker id="ahd" markerWidth="8" markerHeight="7" refX="7" refY="3.5" orient="auto">
      <polygon points="0 0, 8 3.5, 0 7" fill="rgba(255,255,255,0.25)"/>
    </marker>
  </defs>

  
  <rect x="144" y="47" width="256" height="130" rx="14" fill="#1e1f21" stroke="rgba(255,255,255,0.08)" strokeWidth="1.5"/>
  <text x="272" y="65" textAnchor="middle" fill="#555558" fontSize="9" fontFamily="ui-monospace, monospace" letterSpacing="2">GUAVA CLOUD</text>

  
  <rect x="160" y="72" width="224" height="82" rx="8" fill="#272728" stroke="rgba(26,147,254,0.3)" strokeWidth="1.5"/>
  <text x="272" y="110" textAnchor="middle" fill="#1a93fe" fontSize="14" fontFamily="ui-monospace, monospace" fontWeight="700">Dialog System</text>
  <text x="272" y="132" textAnchor="middle" fill="#555558" fontSize="10" fontFamily="ui-monospace, monospace">audio · STT · LLM · TTS</text>

  
  <circle cx="65" cy="115" r="32" fill="#272728" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5"/>
  
  <path d="M 51,113 C 51,103 58,97 65,97 C 72,97 79,103 79,113" fill="none" stroke="#dadada" strokeWidth="1.8" strokeLinecap="round"/>
  <rect x="47" y="113" width="8" height="12" rx="4" fill="#272728" stroke="#dadada" strokeWidth="1.5"/>
  <rect x="75" y="113" width="8" height="12" rx="4" fill="#272728" stroke="#dadada" strokeWidth="1.5"/>
  <text x="65" y="168" textAnchor="middle" fill="#acacac" fontSize="11" fontFamily="ui-monospace, monospace">Caller</text>

  
  <line x1="97" y1="111" x2="137" y2="111" stroke="#acacac" strokeWidth="1.5"/>
  <polygon points="144,111 137,109 137,113" fill="#acacac"/>
  <line x1="104" y1="119" x2="144" y2="119" stroke="#acacac" strokeWidth="1.5"/>
  <polygon points="97,119 104,117 104,121" fill="#acacac"/>
  <text x="120" y="103" textAnchor="middle" fill="#555558" fontSize="9" fontFamily="ui-monospace, monospace">audio</text>

  
  <line x1="400" y1="111" x2="458" y2="111" stroke="#acacac" strokeWidth="1.5"/>
  <polygon points="465,111 458,109 458,113" fill="#acacac"/>
  <line x1="407" y1="119" x2="465" y2="119" stroke="#acacac" strokeWidth="1.5"/>
  <polygon points="400,119 407,117 407,121" fill="#acacac"/>
  <text x="432" y="103" textAnchor="middle" fill="#555558" fontSize="9" fontFamily="ui-monospace, monospace">WebSocket</text>

  
  <rect x="465" y="72" width="186" height="82" rx="8" fill="#272728" stroke="rgba(255,255,255,0.12)" strokeWidth="1.5"/>
  <text x="558" y="108" textAnchor="middle" fill="#dadada" fontSize="13" fontFamily="ui-monospace, monospace" fontWeight="700">Your Expert</text>
  <text x="558" y="130" textAnchor="middle" fill="#555558" fontSize="10" fontFamily="ui-monospace, monospace">Python · TypeScript · ...</text>

  
  <line x1="558" y1="154" x2="465" y2="207" stroke="rgba(255,255,255,0.2)" strokeWidth="1.2" strokeDasharray="5 3" markerEnd="url(#ahd)"/>
  <line x1="558" y1="154" x2="650" y2="207" stroke="rgba(255,255,255,0.2)" strokeWidth="1.2" strokeDasharray="5 3" markerEnd="url(#ahd)"/>

  
  <rect x="385" y="210" width="160" height="56" rx="8" fill="#1e1f21" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
  <text x="465" y="234" textAnchor="middle" fill="#dadada" fontSize="11" fontFamily="ui-monospace, monospace" fontWeight="600">Your Infrastructure</text>
  <text x="465" y="252" textAnchor="middle" fill="#555558" fontSize="9.5" fontFamily="ui-monospace, monospace">local or self-hosted</text>

  
  <text x="559" y="242" textAnchor="middle" fill="#555558" fontSize="9" fontFamily="ui-monospace, monospace">or</text>

  
  <rect x="573" y="210" width="152" height="56" rx="8" fill="#1e1f21" stroke="rgba(26,147,254,0.35)" strokeWidth="1.5"/>
  <text x="649" y="234" textAnchor="middle" fill="#dadada" fontSize="11" fontFamily="ui-monospace, monospace" fontWeight="600">Guava Hosting</text>
  <text x="649" y="252" textAnchor="middle" fill="#555558" fontSize="9.5" fontFamily="ui-monospace, monospace">managed by Guava</text>

  
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" path="M 97,111 L 144,111" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" begin="-0.75s" path="M 97,111 L 144,111" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" begin="-0.75s" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" path="M 144,119 L 97,119" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" begin="-0.75s" path="M 144,119 L 97,119" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" begin="-0.75s" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>

  
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" path="M 400,111 L 465,111" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" begin="-0.75s" path="M 400,111 L 465,111" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" begin="-0.75s" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" path="M 465,119 L 400,119" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
  <circle r="2.5" fill="#1a93fe">
    <animateMotion dur="1.5s" repeatCount="indefinite" calcMode="linear" begin="-0.75s" path="M 465,119 L 400,119" />
    <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" begin="-0.75s" keyTimes="0;0.1;0.9;1" values="0;1;1;0" calcMode="linear" />
  </circle>
</svg>

### The Dialog System

The Dialog System is Guava's managed service running in the cloud. It handles everything time-sensitive during a call: receiving the caller's audio, transcribing it, synthesizing a response, and streaming it back to the caller.

Because the entire pipeline runs as a fully integrated architecture rather than a chain of off-the-shelf APIs, the Dialog System delivers best-in-class latency and naturalness.

### The Expert

The Expert is the code you write. Using the [Guava SDK](/docs/agent), it connects to the Dialog System over a persistent WebSocket and steers the agent in real time.

Because your Expert is just code, you can do anything: query a CRM or database, hit an external API, or chain into another specialized AI sub-agent.
The Dialog System always interacts with your Expert asynchronously, so you can spend time on complex tasks and reasoning without the caller ever noticing a pause.

During development, your Expert runs on your local machine, and Guava routes calls to it directly. You can rapidly iterate by changing the code and restarting the process — no public web server or ngrok required.

#### Structured Callbacks

<ExpertAnimation />

As the Dialog System converses with the caller in natural language, it maintains a separate communication channel with your Expert.
This channel consists of callbacks that follow a consistent structure and schema, and are designed to be plugged into backend systems like RAG and intent recognition.
You decide which callbacks your Expert can handle — all are optional, and the Dialog System will adapt appropriately.

export const ARCH_CALLBACKS_PY = `@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    # The agent will invoke this when the caller asks a question that can't be
    # answered from the current context. Use our ready-to-use RAG module. Or
    # plug in your own custom one.
    return document_qa.ask(question)

@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> list[SuggestedAction]:
    # The agent will invoke this callback when the caller requests a new action.
    # Use our ready-to-use intent classification system. Or plug in a custom one.
    return intent_recognizer.classify(request)`;

export const ARCH_CALLBACKS_TS = `agent.onQuestion(async (call: guava.Call, question: string) => {
  // The agent will invoke this when the caller asks a question that can't be
  // answered from the current context. Use our ready-to-use RAG module. Or
  // plug in your own custom one.
  return await documentQA.ask(question);
});

agent.onActionRequest(async (call: guava.Call, request: string) => {
  // The agent will invoke this callback when the caller requests a new action.
  // Use our ready-to-use intent classification system. Or plug in a custom one.
  return await intentRecognizer.classify(request);
});`;

<CodeTabs
  python={{ code: ARCH_CALLBACKS_PY, filename: "expert.py" }}
  typescript={{ code: ARCH_CALLBACKS_TS, filename: "expert.ts" }}
/>

If you want ready-to-use implementations of these callbacks, you can use our helper library which contains implementations of RAG, intent recognition, and more.
But all of these are optional modules and we encourage you to build your own domain specific versions.

#### Assign Tasks to your Agents

Instead of using a single large prompt for your agent, Guava recommends that you use [Tasks](./tasks).
A task is a checklist of items that you assign to your agent. These items can include things to say to the caller, as well as information to collect as [Fields](./field).
You will receive a callback when your Agent has completed your task and is awaiting more instructions.

export const ARCH_TASK_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_task(
        "waitlist",
        objective="Add callers to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text"),
            guava.Field(key="party_size", field_type="integer"),
            guava.Field(key="phone_number", field_type="text"),
            "Read the phone number back to the caller to confirm.",
        ],
    )

@agent.on_task_complete("waitlist")
def on_waitlist_done(call: guava.Call):
    print("Added caller to waitlist:", call.get_field("caller_name"))
    # End the call, transfer, or chain into another task.
    call.hangup("Thank the caller and let them know we'll text when their table is ready.")`;

export const ARCH_TASK_TS = `agent.onCallStart(async (call) => {
  await call.setTask({
    taskId: "waitlist",
    objective: "Add callers to the waitlist.",
    checklist: [
      guava.Field({ key: "caller_name", fieldType: "text" }),
      guava.Field({ key: "party_size", fieldType: "integer" }),
      guava.Field({ key: "phone_number", fieldType: "text" }),
      "Read the phone number back to the caller to confirm.",
    ],
  });
});

agent.onTaskComplete("waitlist", async (call) => {
  console.log("Added caller to waitlist:", await call.getField("caller_name"));
  // End the call, transfer, or chain into another task.
  await call.hangup("Thank the caller and let them know we'll text when their table is ready.");
});`;

<CodeTabs
  python={{ code: ARCH_TASK_PY, filename: "expert.py" }}
  typescript={{ code: ARCH_TASK_TS, filename: "expert.ts" }}
/>

### Deploying your Expert

When it's time to move to production, you'll want your Expert deployed in a highly-available configuration, ready to handle calls at any time. Because Guava Experts only make outbound connections, it's easy to run an Expert behind a NAT or firewall.

You have two options for deploying your Expert:

- **Your Infrastructure** — deploy to your own servers, VM, or serverless compute platform. You control the environment.
- **Guava Hosting** — push your Expert with a single [`guava deploy`](/docs/cli-reference) command and Guava manages the rest, including horizontal scaling and redundancy.

See the [Deployment guide](/docs/deployment) for a full walkthrough of both options.

### What to read next

- The [Quickstart](/docs/quickstart) shows you how to set up your dev environment and create your first agent.
- The [Example Walkthroughs](/docs/inbound-rag-example) show full Expert implementations for common scenarios, including Q&A and scheduling.
- Once you're comfortable with the basics, the [SDK Reference](/docs/runner) covers every callback and command in detail.

<AutoNextLink currentSection="architecture-overview" />


---

<!-- section: quickstart -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { AutoNextLink, Callout, Prose } from '../views/docs/prose';
import { PlatformTabs } from '../views/docs/PlatformTabs';
import { ManualInstallDownloads } from '../views/docs/ManualInstallDownloads';

## Quickstart

<Callout>
The recommended way to build Guava voice agents is using the Guava CLI, which bootstraps projects and installs the SDK.
If you’d rather not install the CLI, you can skip to the [direct SDK installation guide](./sdk-installation) instead.
</Callout>

### Install the CLI

Install the CLI using one of the supported methods for your platform.

<PlatformTabs
  macosContent={<>
    <Prose>If you have Homebrew installed, you can install the CLI from our tap.</Prose>
    <CodeBlock code={`brew install goguava-ai/tap/guava`} language="bash" />
    <Prose>If not, you can install using our provided shell script.</Prose>
    <CodeBlock code={`# Installs to \`~/.local/bin/guava\`
curl -fsSL https://goguava.ai/install.sh | sh`} language="bash" />
  </>}
  linuxContent={<>
    <Prose>For Linux and WSL, run the installation shell script.</Prose>
    <CodeBlock code={`# Installs to \`~/.local/bin/guava\`
curl -fsSL https://goguava.ai/install.sh | sh`} language="bash" />
  </>}
  windowsContent={<>
    <Prose>Run the installation script from a PowerShell console.</Prose>
    <CodeBlock code="irm https://goguava.ai/install.ps1 | iex" language="bash" />
  </>}
  manualContent={<>
    <Prose>Download the binary for your platform directly. After downloading, make the file executable and place it somewhere on your <code>PATH</code> (e.g. <code>~/.local/bin/</code>).</Prose>
    <ManualInstallDownloads />
  </>}
/>

### Authenticate the CLI

This command will open a browser where you can log in or create an account.

<CodeBlock code="guava login" language="bash" />

### Create an Agent

Scaffold a new agent project with starter code.

<CodeBlock code="guava create my-agent" language="bash" />

### Run your Agent

<CodeBlock code="guava run ./my-agent" language="bash" />

You can stop your agent by pressing Ctrl-C.

<Callout>
If you're having trouble running your agent, try deploying.
</Callout>

### [Optional] Deploy your Agent

To deploy your agent on Guava's server go to the [Deployment guide](./deployment).

<AutoNextLink currentSection="quickstart" />


---

<!-- section: sdk-installation -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { LanguageTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, Prose } from '../views/docs/prose';

## Quickstart (SDK-Only)

<Callout>
The recommended way to build Guava voice agents is using the [Guava CLI](./quickstart), which bootstraps projects and installs the SDK.
This guide explains how to install the SDK directly if you’d prefer not to use the CLI.
</Callout>

### Create an account

Sign up for an account at [app.goguava.ai](https://app.goguava.ai).

### Install the SDK

Guava provides SDKs for Python and TypeScript. Choose your language and package manager.

<LanguageTabs
  pythonContent={<>
    <CodeBlock code={
`uv add guava-sdk      # Install using uv (Recommended)
pip install guava-sdk # Install using pip
poetry add guava-sdk  # Install using poetry`} language="bash" />
  </>}
  typescriptContent={<>
    <CodeBlock code={
`npm install @guava-ai/guava-sdk # Install using npm
yarn add @guava-ai/guava-sdk    # Install using yarn
pnpm add @guava-ai/guava-sdk    # Install using pnpm`} language="bash" />
  </>}
/>

### Set Environment Variables

The SDK reads credentials from the environment automatically. Set these before running any Guava scripts.

<CodeBlock code={`export GUAVA_API_KEY="gva-..." # Set to your API key.
export GUAVA_AGENT_NUMBER="+15551234567" # Used by SDK examples. Set to your purchased number.`} filename=".env" language="bash" />

Create an API key using the [API Keys](https://app.goguava.ai/dashboard/api-keys) page. Purchase a phone number using the [Phone Numbers](https://app.goguava.ai/dashboard/phone-numbers) page.


### Add the coding agent starter kit

Download the Guava coding agent starter kit into your project. It contains plain-text API docs sized for AI coding assistants.

<CodeBlock code={`curl -o guava-docs.md https://goguava.ai/docs/coding-agent-starter.md`} language="bash" />

### Run an Example

<LanguageTabs
  pythonContent={<>
    <Prose>Examples can be run directly from the Python SDK. You can browse the examples <a href="https://github.com/goguava-ai/python-sdk/tree/main/guava/examples">on GitHub</a>.</Prose>
    <CodeBlock code={  
`# This will attach your agent to a phone number. Dial that number to talk to your agent.
python -m guava.examples.restaurant_waitlist --phone

# Start a test call with a local audio device.
python -m guava.examples.restaurant_waitlist --local

# This will attach your agent to a WebRTC code.
# You can dial it from the browser at https://app.goguava.ai/debug-webrtc
python -m guava.examples.restaurant_waitlist --webrtc

# Start an in-terminal text-only chat for testing.
python -m guava.examples.restaurant_waitlist --chat`} language="bash" />
  </>}
  typescriptContent={<>
    <Prose>Examples can be run directly from the TypeScript SDK. You can browse the examples <a href="https://github.com/goguava-ai/typescript-sdk/tree/main/examples">on GitHub</a></Prose>
    <CodeBlock code={
`# This will attach your agent to a phone number. Dial that number to talk to your agent.
npx @guava-ai/guava-sdk restaurant-waitlist phone

# Start a test call with a local audio device.
npx @guava-ai/guava-sdk restaurant-waitlist local

# This will attach your agent to a WebRTC code.
# You can dial it from the browser at https://app.goguava.ai/debug-webrtc
npx @guava-ai/guava-sdk restaurant-waitlist webrtc

# Start an in-terminal text-only chat for testing.
npx @guava-ai/guava-sdk restaurant-waitlist chat`} language="bash" />
  </>}
/>

<AutoNextLink currentSection="sdk-installation" />

---

<!-- section: inbound-rag-example -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, Prose, AutoNextLink } from '../views/docs/prose';

## Inbound Example w/ RAG

In this example, we'll build an inbound voice agent for a fictional property insurance company.
Callers can ask any question about their policy and receive accurate answers sourced from a policy document.

### Define the Agent

`guava.Agent` is our starting point for building Guava agents. We'll start by creating one with some basic background details.

export const AGENT_PY = `import guava

agent = guava.Agent(
    organization="Harper Valley Property Insurance",
    purpose="Answer questions regarding property insurance policy until there are no more questions",
)`;

export const AGENT_TS = `import * as guava from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  organization: "Harper Valley Property Insurance",
  purpose: "Answer questions regarding property insurance policy until there are no more questions",
});`;

<CodeTabs
  python={{ code: AGENT_PY, filename: "property_insurance.py" }}
  typescript={{ code: AGENT_TS, filename: "property-insurance.ts" }}
/>

<Callout>
Guava discourages long system prompts that try to cover every scenario. The `purpose` is intentionally short and designed to orient the agent.
</Callout>

### Set up DocumentQA

Next, we initialize a `DocumentQA` instance with the policy document. `DocumentQA` is a built-in RAG that covers a lot of simple use cases. It's a fully pluggable component
and we expect many users will bring their own RAG system.

export const QA_PY = `from guava.helpers.rag import DocumentQA
from guava.examples.example_data import PROPERTY_INSURANCE_POLICY

document_qa = DocumentQA(documents=PROPERTY_INSURANCE_POLICY)`;

export const QA_TS = `import { DocumentQA } from "@guava-ai/guava-sdk/helpers";
import { PROPERTY_INSURANCE_POLICY } from "@guava-ai/guava-sdk/example-data";

const documentQA = new DocumentQA({
  documents: PROPERTY_INSURANCE_POLICY,
  namespace: "harper-valley-property-insurance",
});`;

<CodeTabs
  python={{ code: QA_PY, filename: "property_insurance.py" }}
  typescript={{ code: QA_TS, filename: "property-insurance.ts" }}
/>



### Handle questions with on_question

Whenever the caller asks something the agent cannot answer from context alone, Guava invokes the `on_question` callback with the question in natural language. We forward it to `DocumentQA` and return the answer.

export const ON_QUESTION_PY = `@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    return document_qa.ask(question)`;

export const ON_QUESTION_TS = `agent.onQuestion(async (call: guava.Call, question: string) => {
  return await documentQA.ask(question);
});`;

<CodeTabs
  python={{ code: ON_QUESTION_PY, filename: "property_insurance.py" }}
  typescript={{ code: ON_QUESTION_TS, filename: "property-insurance.ts" }}
/>

The agent remains fully responsive during the lookup — it continues listening and engaging with the caller while waiting for your response. You are not latency-constrained in your `on_question` implementation.

<Callout>
  <span className="text-primary font-semibold">Bring your own RAG.</span> The <code>on_question</code> callback receives a plain string and expects a plain string back — you can plug in any knowledge base, vector store, or model you prefer.
</Callout>

### Start the agent

Finally, we attach the agent to a channel so that we can actually talk to it.

export const RUN_PY = `# Run this to attach your agent to a phone number. Call your agent's number to talk to it.
agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])

# Run this to receive a WebRTC link where you can talk to your agent in the browser.
agent.listen_webrtc()

# Run this to talk to your agent using your local audio device.
agent.call_local()

# Run this to test your agent in a text-based chat session in the terminal (no audio required).
agent.chat()`;

export const RUN_TS = `// Run this to attach your agent to a phone number. Call your agent's number to talk to it.
agent.listenPhone(process.env.GUAVA_AGENT_NUMBER!);

// Run this to receive a WebRTC link where you can talk to your agent in the browser.
agent.listenWebrtc();

// Run this to talk to your agent using your local audio device.
agent.callLocal();

// Run this to test your agent in a text-based chat session in the terminal (no audio required).
agent.chat();`;

<CodeTabs
  python={{ code: RUN_PY, filename: "property_insurance.py" }}
  typescript={{ code: RUN_TS, filename: "property-insurance.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">No web servers required.</span> Guava does not require a public web server to receive inbound calls. All Guava agents can be hosted behind firewalls and NATs.
</Callout>

### Complete example

export const FULL_PY = `import logging
import os
import guava
import argparse

from guava.helpers.rag import DocumentQA
from guava import logging_utils, Agent
from guava.examples.example_data import PROPERTY_INSURANCE_POLICY

logger = logging.getLogger("guava.examples.property_insurance")

agent = Agent(
    organization="Harper Valley Property Insurance",
    purpose="Answer questions regarding property insurance policy until there are no more questions",
)

# This is a built-in knowledge base helper that we will use for this example.
# You can use any RAG system you prefer.
document_qa = DocumentQA(documents=PROPERTY_INSURANCE_POLICY)


# When the Agent is asked a question that it cannot answer, it will invoke the on_question callback.
@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    # Forward the Agent's question to the knowledge base and return the answer.
    # You can plug in any knowledge base system you want here.
    answer = document_qa.ask(question)
    logger.info("RAG answer: %s", answer)
    return answer


if __name__ == "__main__":
    logging_utils.configure_logging()

    # Every Agent can be attached to multiple resources.
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phone", action="store_true", help="Listen for phone calls.")
    group.add_argument("--webrtc", action="store_true", help="Create on a WebRTC code.")
    group.add_argument("--local", action="store_true", help="Start a local call.")
    group.add_argument("--chat", action="store_true", help="Start a text-based chat session for testing.")
    args = parser.parse_args()

    if args.phone:
        agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])
    elif args.webrtc:
        agent.listen_webrtc()
    elif args.chat:
        agent.chat()
    else:
        agent.call_local()`;

export const FULL_TS = `import * as guava from "@guava-ai/guava-sdk";
import { DocumentQA } from "@guava-ai/guava-sdk/helpers";
import { PROPERTY_INSURANCE_POLICY } from "@guava-ai/guava-sdk/example-data";

const agent = new guava.Agent({
  organization: "Harper Valley Property Insurance",
  purpose: "Answer questions regarding property insurance policy until there are no more questions",
});

// This is a built-in knowledge base helper that we will use for this example.
// You can use any RAG system you prefer.
const documentQA = new DocumentQA({
  documents: PROPERTY_INSURANCE_POLICY,
  namespace: "harper-valley-property-insurance",
});

// When the Agent is asked a question that it cannot answer, it will invoke the on_question callback.
agent.onQuestion(async (call: guava.Call, question: string) => {
  // Forward the Agent's question to the knowledge base and return the answer.
  // You can plug in any knowledge base system you want here.
  return await documentQA.ask(question);
});

const args = process.argv.slice(2);
if (args.includes("--webrtc")) {
  agent.listenWebrtc();
} else if (args.includes("--phone")) {
  agent.listenPhone(process.env.GUAVA_AGENT_NUMBER!);
} else if (args.includes("--local")) {
  agent.callLocal();
} else if (args.includes("--chat")) {
  agent.chat();
} else {
  console.error("Usage: guava-example property-insurance --phone | --webrtc | --local | --chat");
  process.exit(1);
}`;

<CodeTabs
  python={{ code: FULL_PY, filename: "property_insurance.py" }}
  typescript={{ code: FULL_TS, filename: "property-insurance.ts" }}
/>

<AutoNextLink currentSection="inbound-rag-example" />


---

<!-- section: inbound-form-filling -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, Prose, AutoNextLink } from '../views/docs/prose';

## Inbound w/ Form Filling

In this example, we'll build an inbound voice agent for a fictional restaurant. Callers can join the waitlist by providing their name, party size, and a callback number — which the agent collects conversationally using a structured task.

### Define the Agent

`guava.Agent` is our starting point for building Guava agents. We'll create one with a name and purpose scoped to the restaurant.

export const AGENT_PY = `import guava

agent = guava.Agent(
    name="Mia",
    organization="Thai Palace",
    purpose="Helping callers join the restaurant waitlist",
)`;

export const AGENT_TS = `import * as guava from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  name: "Mia",
  organization: "Thai Palace",
  purpose: "Helping callers join the restaurant waitlist",
});`;

<CodeTabs
  python={{ code: AGENT_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: AGENT_TS, filename: "restaurant-waitlist.ts" }}
/>

### Accept or reject the call

`on_call_received` fires before the call starts and gives you a chance to accept or reject based on caller info. Here we accept all calls.

export const ACCEPT_PY = `@agent.on_call_received
def on_call_received(call_info: guava.CallInfo) -> guava.IncomingCallAction:
    return guava.AcceptCall()`;

export const ACCEPT_TS = `agent.onCallReceived(async (_callInfo: guava.CallInfo) => {
  return { action: "accept" };
});`;

<CodeTabs
  python={{ code: ACCEPT_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: ACCEPT_TS, filename: "restaurant-waitlist.ts" }}
/>

<Callout>
  If you don't register <code>on_call_received</code>, Guava accepts all calls by default. Implement it only when you need to screen callers or look up information based off the incoming phone number.
</Callout>

### Set up the form

`on_call_start` fires at the beginning of every accepted call. We use `set_task` to hand the agent a structured checklist of fields to collect. The agent gathers each piece of information conversationally — it knows when all fields are filled and automatically moves on.

export const TASK_PY = `@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    call.set_task(
        "waitlist",
        objective="You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text", description="Name for the waitlist"),
            guava.Field(key="party_size", field_type="integer", description="Number of people"),
            guava.Field(
                key="phone_number",
                field_type="text",
                description="Phone number to text when the table is ready",
            ),
            "Read the phone number back to the caller to confirm.",
        ],
    )`;

export const TASK_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.setTask({
    taskId: "waitlist",
    objective: "You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
    checklist: [
      guava.Field({ key: "caller_name", fieldType: "text", description: "Name for the waitlist" }),
      guava.Field({ key: "party_size", fieldType: "integer", description: "Number of people" }),
      guava.Field({
        key: "phone_number",
        fieldType: "text",
        description: "Phone number to text when the table is ready",
      }),
      "Read the phone number back to the caller to confirm.",
    ],
  });
});`;

<CodeTabs
  python={{ code: TASK_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: TASK_TS, filename: "restaurant-waitlist.ts" }}
/>

<Callout>
  The checklist can mix <code>Field</code> objects (typed, named values the agent extracts) with plain strings (freeform instructions the agent follows). Fields are retrievable later via <code>get_field()</code>.
</Callout>

### Handle task completion

`on_task_complete` fires once every field in the checklist is collected. This is the right place to save the data to your backend, trigger a notification, or hang up.

export const COMPLETE_PY = `@agent.on_task_complete("waitlist")
def on_waitlist_done(call: guava.Call) -> None:
    logger.info(
        "Added %s, party of %d, to waitlist.",
        call.get_field("caller_name"),
        call.get_field("party_size"),
    )
    call.hangup("Thank the caller and let them know we'll text when their table is ready.")`;

export const COMPLETE_TS = `agent.onTaskComplete("waitlist", async (call: guava.Call) => {
  logger.info(
    "Added %s, party of %d, to waitlist.",
    await call.getField("caller_name"),
    await call.getField("party_size"),
  );
  await call.hangup("Thank the caller and let them know we'll text when their table is ready.");
});`;

<CodeTabs
  python={{ code: COMPLETE_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: COMPLETE_TS, filename: "restaurant-waitlist.ts" }}
/>

### Start the agent

Attach the agent to a channel to start receiving inbound calls.

export const RUN_PY = `# Run this to attach your agent to a phone number. Call your agent's number to talk to it.
agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])

# Run this to receive a WebRTC link where you can talk to your agent in the browser.
agent.listen_webrtc()

# Run this to talk to your agent using your local audio device.
agent.call_local()

# Run this to test your agent in a text-based chat session in the terminal (no audio required).
agent.chat()`;

export const RUN_TS = `// Run this to attach your agent to a phone number. Call your agent's number to talk to it.
agent.listenPhone(process.env.GUAVA_AGENT_NUMBER!);

// Run this to receive a WebRTC link where you can talk to your agent in the browser.
agent.listenWebrtc();

// Run this to talk to your agent using your local audio device.
agent.callLocal();

// Run this to test your agent in a text-based chat session in the terminal (no audio required).
agent.chat();`;

<CodeTabs
  python={{ code: RUN_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: RUN_TS, filename: "restaurant-waitlist.ts" }}
/>

### Complete example

export const FULL_PY = `import os
import guava
import logging
import argparse
from guava import logging_utils

logger = logging.getLogger("thai_palace")

agent = guava.Agent(
    name="Mia",
    organization="Thai Palace",
    purpose="Helping callers join the restaurant waitlist",
)


@agent.on_call_received
def on_call_received(call_info: guava.CallInfo) -> guava.IncomingCallAction:
    return guava.AcceptCall()


@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    call.set_task(
        "waitlist",
        objective="You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text", description="Name for the waitlist"),
            guava.Field(key="party_size", field_type="integer", description="Number of people"),
            guava.Field(
                key="phone_number",
                field_type="text",
                description="Phone number to text when the table is ready",
            ),
            "Read the phone number back to the caller to confirm.",
        ],
    )


@agent.on_task_complete("waitlist")
def on_waitlist_done(call: guava.Call) -> None:
    logger.info(
        "Added %s, party of %d, to waitlist.",
        call.get_field("caller_name"),
        call.get_field("party_size"),
    )
    call.hangup("Thank the caller and let them know we'll text when their table is ready.")


if __name__ == "__main__":
    logging_utils.configure_logging()

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phone", action="store_true", help="Listen for phone calls.")
    group.add_argument("--webrtc", action="store_true", help="Create on a WebRTC code.")
    group.add_argument("--local", action="store_true", help="Start a local call.")
    group.add_argument("--chat", action="store_true", help="Start a text-based chat session for testing.")
    args = parser.parse_args()

    if args.phone:
        agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])
    elif args.webrtc:
        agent.listen_webrtc()
    elif args.chat:
        agent.chat()
    else:
        agent.call_local()`;

export const FULL_TS = `import * as guava from "@guava-ai/guava-sdk";
import { getDefaultLogger } from "@guava-ai/guava-sdk";

const logger = getDefaultLogger();

const agent = new guava.Agent({
  name: "Mia",
  organization: "Thai Palace",
  purpose: "Helping callers join the restaurant waitlist",
});

agent.onCallReceived(async (_callInfo: guava.CallInfo) => {
  return { action: "accept" };
});

agent.onCallStart(async (call: guava.Call) => {
  await call.setTask({
    taskId: "waitlist",
    objective: "You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
    checklist: [
      guava.Field({ key: "caller_name", fieldType: "text", description: "Name for the waitlist" }),
      guava.Field({ key: "party_size", fieldType: "integer", description: "Number of people" }),
      guava.Field({
        key: "phone_number",
        fieldType: "text",
        description: "Phone number to text when the table is ready",
      }),
      "Read the phone number back to the caller to confirm.",
    ],
  });
});

agent.onTaskComplete("waitlist", async (call: guava.Call) => {
  logger.info(
    "Added %s, party of %d, to waitlist.",
    await call.getField("caller_name"),
    await call.getField("party_size"),
  );
  await call.hangup("Thank the caller and let them know we'll text when their table is ready.");
});

const args = process.argv.slice(2);
if (args.includes("--webrtc")) {
  agent.listenWebrtc();
} else if (args.includes("--phone")) {
  agent.listenPhone(process.env.GUAVA_AGENT_NUMBER!);
} else if (args.includes("--local")) {
  agent.callLocal();
} else if (args.includes("--chat")) {
  agent.chat();
} else {
  console.error("Usage: guava-example restaurant-waitlist --phone | --webrtc | --local | --chat");
  process.exit(1);
}`;

<CodeTabs
  python={{ code: FULL_PY, filename: "restaurant_waitlist.py" }}
  typescript={{ code: FULL_TS, filename: "restaurant-waitlist.ts" }}
/>

<AutoNextLink currentSection="inbound-form-filling" />


---

<!-- section: outbound-scheduling -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, Prose, AutoNextLink } from '../views/docs/prose';

## Outbound w/ Scheduling

In this example, we'll build an outbound voice agent for a dental office. The agent calls patients to help them schedule appointments.

### Define the Agent

`guava.Agent` is our starting point for building Guava agents. We'll create one for this example.

export const AGENT_PY = `import guava

agent = guava.Agent(
    organization="Bright Smile Dental",
    purpose="Call patients to help them schedule a dental appointment.",
)`;

export const AGENT_TS = `import * as guava from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  organization: "Bright Smile Dental",
  purpose: "You are calling patients to help them schedule a dental appointment",
});`;

<CodeTabs
  python={{ code: AGENT_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: AGENT_TS, filename: "scheduling-outbound.ts" }}
/>

### Set up DatetimeFilter

`DatetimeFilter` is a built-in helper that accepts a natural-language availability query (e.g. "Tuesdays work best") and returns a short list of matching slots from your source data. In a production system you would swap this for a call to your own scheduling backend.

export const FILTER_PY = `from guava.helpers.openai import DatetimeFilter
from guava.examples.example_data import MOCK_APPOINTMENTS

datetime_filter = DatetimeFilter(source_list=MOCK_APPOINTMENTS)`;

export const FILTER_TS = `import { DatetimeFilter } from "@guava-ai/guava-sdk/helpers";
import { mockAppointmentsForFuture } from "@guava-ai/guava-sdk/example-data";

const datetimeFilter = new DatetimeFilter({
  sourceList: mockAppointmentsForFuture(),
});`;

<CodeTabs
  python={{ code: FILTER_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: FILTER_TS, filename: "scheduling-outbound.ts" }}
/>

### Reach the right person

`on_call_start` fires at the beginning of every outbound call. We read the patient's name from the call variables and invoke `reach_person`, which instructs the agent to confirm it is speaking with the intended recipient before proceeding. Later in this example, we'll see how to set the `patient_name` variable.

export const START_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.reach_person(
        contact_full_name=call.get_variable("patient_name"),
    )`;

export const START_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.reachPerson(await call.getVariable("patientName"));
});`;

<CodeTabs
  python={{ code: START_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: START_TS, filename: "scheduling-outbound.ts" }}
/>

<Callout>
  Under the hood `reach_person()` is just a call to `set_task()`. You can replace `reach_person()` with your own [Task](./tasks) if you need custom behavior here.
</Callout>

### Handle the reach-person outcome

`on_reach_person` fires once the agent has determined whether the intended person is available. If they are, we set a task to collect an appointment time. If not, we hang up gracefully.

export const REACH_PY = `@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str) -> None:
    if outcome == "unavailable":
        call.hangup("Apologize for your mistake and hang up the call.")
    elif outcome == "available":
        call.set_task(
            "schedule_appointment",
            checklist=[
                "Tell them that it's been a while since their regular cleaning with Dr. Teeth.",
                guava.Field(
                    key="appointment_time",
                    field_type="calendar_slot",
                    description="Find a time that works for the caller",
                    searchable=True,
                ),
                "Tell them their appointment has been confirmed and answer any questions before ending the call.",
            ],
        )`;

export const REACH_TS = `agent.onReachPerson(async (call: guava.Call, outcome: string) => {
  if (outcome === "available") {
    await call.setTask({
      taskId: "schedule_appointment",
      checklist: [
        "Tell them that it's been a while since their regular cleaning with Dr. Teeth.",
        guava.Field({
          key: "appointment_time",
          fieldType: "calendar_slot",
          description: "Find a time that works for the caller",
          searchable: true,
        }),
        "Tell them their appointment has been confirmed and answer any questions before ending the call.",
      ],
    });
  } else {
    await call.hangup("Apologize for your mistake and hang up the call.");
  }
});`;

<CodeTabs
  python={{ code: REACH_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: REACH_TS, filename: "scheduling-outbound.ts" }}
/>

### Register an `on_search_query` handler

The `appointment_time` field has a special attribute `searchable=True` set. This turns the field into a "Search Field". Instead of providing a fixed list of choices, we will register an `on_search_query` handler.

The agent will invoke this handler to generate possible candidates for filling the field - at each invocation the agent provides a natural-language search query for us to match against.

In this example, we can simply forward that query to DatetimeFilter and return the result.

export const SEARCH_PY = `@agent.on_search_query("appointment_time")
def search_appointments(call: guava.Call, query: str):
    return datetime_filter.filter(query, max_results=3)`;

export const SEARCH_TS = `agent.onSearchQuery("appointment_time", async (_call, query) => {
  return datetimeFilter.filter(query, { maxResults: 3 });
});`;

<CodeTabs
  python={{ code: SEARCH_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: SEARCH_TS, filename: "scheduling-outbound.ts" }}
/>

The agent may call this handler multiple times if the patient rejects the initial options or refines their availability.

### Handle task completion

`on_task_complete` fires once every item in the checklist is resolved. This is where you'd write the confirmed slot back to your database, trigger a confirmation SMS, or perform any other post-booking actions.

export const COMPLETE_PY = `@agent.on_task_complete("schedule_appointment")
def on_appointment_scheduled(call: guava.Call):
    call.hangup("Thank them for their time and hang up the call.")`;

export const COMPLETE_TS = `agent.onTaskComplete("schedule_appointment", async (call) => {
  await call.hangup("Thank them for their time and hang up the call.");
});`;

<CodeTabs
  python={{ code: COMPLETE_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: COMPLETE_TS, filename: "scheduling-outbound.ts" }}
/>

### Place the outbound call

Use `call_phone` to initiate the call. Here is where you set initial values for variables - they'll be available inside your handlers via `get_variable()`.

export const RUN_PY = `# Run agent.call_phone to start the outbound call, setting our initial variables.
agent.call_phone(
    from_number=os.environ["GUAVA_AGENT_NUMBER"],
    to_number=args.phone,
    variables={"patient_name": args.name},
)

# Or, test your agent in a text-based chat session in the terminal (no audio required).
agent.chat(variables={"patient_name": args.name})`;

export const RUN_TS = `agent.callPhone(process.env.GUAVA_AGENT_NUMBER, toNumber, {
  patientName: patientName,
});

// Or, test your agent in a text-based chat session in the terminal (no audio required).
agent.chat({ patientName: patientName });`;

<CodeTabs
  python={{ code: RUN_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: RUN_TS, filename: "scheduling-outbound.ts" }}
/>

<Callout>
If you intend to dial multiple participants, use [Campaigns](./campaign) instead of individual outbound calls. Campaigns offer settings for automatic retries, call windows, multiple origin phone numbers, and concurrency control.
</Callout>

### Complete example

export const FULL_PY = `import logging
import os
import argparse
import guava

from guava import logging_utils, Agent
from guava.examples.example_data import MOCK_APPOINTMENTS
from guava.helpers.openai import DatetimeFilter

logger = logging.getLogger("guava.examples.scheduling_outbound")

agent = Agent(
    organization="Bright Smile Dental",
    purpose="Call patients to help them schedule a dental appointment.",
)
datetime_filter = DatetimeFilter(source_list=MOCK_APPOINTMENTS)


@agent.on_call_start
def on_call_start(call: guava.Call):
    call.reach_person(
        contact_full_name=call.get_variable("patient_name"),
    )


@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str) -> None:
    if outcome == "unavailable":
        call.hangup("Apologize for your mistake and hang up the call.")
    elif outcome == "available":
        call.set_task(
            "schedule_appointment",
            checklist=[
                "Tell them that it's been a while since their regular cleaning with Dr. Teeth.",
                guava.Field(
                    key="appointment_time",
                    field_type="calendar_slot",
                    description="Find a time that works for the caller",
                    searchable=True,
                ),
                "Tell them their appointment has been confirmed and answer any questions before ending the call.",
            ],
        )


@agent.on_search_query("appointment_time")
def search_appointments(call: guava.Call, query: str):
    return datetime_filter.filter(query, max_results=3)


@agent.on_task_complete("schedule_appointment")
def on_appointment_scheduled(call: guava.Call):
    call.hangup("Thank them for their time and hang up the call.")


if __name__ == "__main__":
    logging_utils.configure_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("phone", type=str, help="Phone number to call.")
    parser.add_argument("name", nargs="?", help="Name of the patient", default="Benjamin Buttons")
    args = parser.parse_args()

    agent.call_phone(
        from_number=os.environ["GUAVA_AGENT_NUMBER"],
        to_number=args.phone,
        variables={"patient_name": args.name},
    )`;

export const FULL_TS = `import * as guava from "@guava-ai/guava-sdk";
import { DatetimeFilter } from "@guava-ai/guava-sdk/helpers";
import { mockAppointmentsForFuture } from "@guava-ai/guava-sdk/example-data";

const agent = new guava.Agent({
  organization: "Bright Smile Dental",
  purpose: "You are calling patients to help them schedule a dental appointment",
});

const datetimeFilter = new DatetimeFilter({
  sourceList: mockAppointmentsForFuture(),
});

agent.onCallStart(async (call: guava.Call) => {
  await call.reachPerson(await call.getVariable("patientName"));
});

agent.onSearchQuery("appointment_time", async (_call, query) => {
  return datetimeFilter.filter(query, { maxResults: 3 });
});

agent.onReachPerson(async (call: guava.Call, outcome: string) => {
  if (outcome === "available") {
    await call.setTask({
      taskId: "schedule_appointment",
      checklist: [
        "Tell them that it's been a while since their regular cleaning with Dr. Teeth.",
        guava.Field({
          key: "appointment_time",
          fieldType: "calendar_slot",
          description: "Find a time that works for the caller",
          searchable: true,
        }),
        "Tell them their appointment has been confirmed and answer any questions before ending the call.",
      ],
    });
  } else {
    await call.hangup("Apologize for your mistake and hang up the call.");
  }
});

agent.onTaskComplete("schedule_appointment", async (call) => {
  await call.hangup("Thank them for their time and hang up the call.");
});

export async function run(args: string[]) {
  if (args.includes("--chat")) {
    const patientName = args[args.indexOf("--chat") + 1] ?? "Benjamin Buttons";
    await agent.chat({ patientName });
    return;
  }

  const [toNumber, patientName = "Benjamin Buttons"] = args;

  if (!toNumber) {
    console.error("Usage: guava-example scheduling-outbound <phone> [name]");
    console.error("       guava-example scheduling-outbound --chat [name]");
    process.exit(1);
  }

  agent.callPhone(process.env.GUAVA_AGENT_NUMBER, toNumber, {
    patientName: patientName,
  });
}

if (import.meta.main) {
  run(process.argv.slice(2));
}`;

<CodeTabs
  python={{ code: FULL_PY, filename: "scheduling_outbound.py" }}
  typescript={{ code: FULL_TS, filename: "scheduling-outbound.ts" }}
/>

<AutoNextLink currentSection="outbound-scheduling" />


---

<!-- section: agent -->

import { CodeTabs, LanguageAlternate } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const AGENT_EX_PY = `import os
import guava

# Define our agent
agent = guava.Agent(
    name="Nova",
    organization="Acme Corp",
    purpose="Help customers with their orders.",
    pronunciations={"Acme": "Ack-mee", "Waukesha": "/ˈwɔːkɪʃɔː/"},
)

# Register handlers
@agent.on_call_start
def on_call_start(call: guava.Call):
    ...

# Attach to a channel
agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])`;

export const AGENT_EX_TS = `import * as guava from "@guava-ai/guava-sdk";

// Define our agent
const agent = new guava.Agent({
  name: "Nova",
  organization: "Acme Corp",
  purpose: "Help customers with their orders.",
  pronunciations: {"Acme": "Ack-mee", "Waukesha": "/ˈwɔːkɪʃɔː/"},
});

// Register handlers
agent.onCallStart(async (call) => {
  ...
});

// Attach to a channel
agent.listenPhone(process.env.GUAVA_AGENT_NUMBER!);`;

## Agent

`guava.Agent` is the entrypoint for creating Guava voice agents. Create an `Agent` instance, attach handlers, then attach to a channel.

<CodeTabs
  python={{ code: AGENT_EX_PY, filename: "agent.py" }}
  typescript={{ code: AGENT_EX_TS, filename: "agent.ts" }}
/>

export const AGENT_SIG_PY = `guava.Agent(
    # The name the agent uses to identify itself to callers.
    name: str | None = None,

    # The organization the agent represents.
    organization: str | None = None,

    # High-level description of the agent's role.
    purpose: str | None = None,

    # Map words to custom pronunciations.
    pronunciations: dict[str, str] | None = None,

    # How quickly the agent speaks.
    speech_speed: Literal["x-slow", "slow", "medium", "fast", "x-fast"] | None = None,
)`;

export const AGENT_SIG_TS = `new guava.Agent({
  // The name the agent uses to identify itself to callers.
  name?: string,

  // The organization the agent represents.
  organization?: string,

  // High-level description of the agent's role.
  purpose?: string,

  // Map words to custom pronunciations.
  pronunciations?: Record<string, string>,

  // How quickly the agent speaks.
  speechSpeed?: "x-slow" | "slow" | "medium" | "fast" | "x-fast",
})`;

### Constructor

Use the constructor parameters to configure your Agent's persona and goal.

<CodeTabs
  python={{ code: AGENT_SIG_PY }}
  typescript={{ code: AGENT_SIG_TS }}
/>

Custom pronunciations can be passed as either International Phonetic Alphabet (IPA) transcriptions, which must be marked with opening and closing slashes (`/`), or phonetic respellings.

<LanguageAlternate pythonContent={<code>speech_speed</code>} typescriptContent={<code>speechSpeed</code>} /> sets how quickly the agent speaks, as one of the presets `"x-slow"`, `"slow"`, `"medium"` (the default), `"fast"`, or `"x-fast"`. The preset applies to every call the agent handles; use <LanguageAlternate pythonContent={<a href="./set-persona"><code>call.set_persona()</code></a>} typescriptContent={<a href="./set-persona"><code>call.setPersona()</code></a>} /> to change it for a single call.

### Handlers

Register handlers to control and react to the call in real-time.

| Handler | Description |
|---------|-------------|
| <LanguageAlternate pythonContent={<code>on_call_received</code>} typescriptContent={<code>onCallReceived</code>} /> | This handler is invoked on incoming calls. You can choose whether to reject or accept the call. The default behavior if not provided is to accept every call. |
| <LanguageAlternate pythonContent={<code>on_call_start</code>} typescriptContent={<code>onCallStart</code>} /> | Called when a call begins. Unlike <LanguageAlternate pythonContent={<code>on_call_received</code>} typescriptContent={<code>onCallReceived</code>} />, this handler is invoked for both incoming and outgoing calls. Use this handler to set initial tasks and context for the Agent. |
| <LanguageAlternate pythonContent={<a href="./on-caller-speech"><code>on_caller_speech</code></a>} typescriptContent={<a href="./on-caller-speech"><code>onCallerSpeech</code></a>} /> | Called each time the caller speaks. |
| <LanguageAlternate pythonContent={<a href="./on-agent-speech"><code>on_agent_speech</code></a>} typescriptContent={<a href="./on-agent-speech"><code>onAgentSpeech</code></a>} /> | Called each time the agent speaks. |
| <LanguageAlternate pythonContent={<a href="./on-question"><code>on_question</code></a>} typescriptContent={<a href="./on-question"><code>onQuestion</code></a>} /> | Called when the caller asks the agent a question it cannot answer from context alone. The provided answer is relayed back to the caller. |
| <LanguageAlternate pythonContent={<a href="./on-task-complete"><code>on_task_complete</code></a>} typescriptContent={<a href="./on-task-complete"><code>onTaskComplete</code></a>} /> | Called when the Agent completes a [Task](./tasks) previously set using <LanguageAlternate pythonContent={<code>call.set_task</code>} typescriptContent={<code>call.setTask</code>} />. |
| <LanguageAlternate pythonContent={<code>on_search_query</code>} typescriptContent={<code>onSearchQuery</code>} /> | Provide dynamic search results for a searchable [Field](./field). |
| <LanguageAlternate pythonContent={<a href="./on-action-request-execute"><code>on_action_request</code> / <code>on_action</code></a>} typescriptContent={<a href="./on-action-request-execute"><code>onActionRequest</code> / <code>onAction</code></a>} /> | Called when the caller asks for a specific action, e.g. "can I reset my password?" |
| <LanguageAlternate pythonContent={<a href="./on-session-end"><code>on_session_end</code></a>} typescriptContent={<a href="./on-session-end"><code>onSessionEnd</code></a>} /> | Called when the session ends. Read <LanguageAlternate pythonContent={<code>event.termination_reason</code>} typescriptContent={<code>event.terminationReason</code>} /> to find out why the call ended. |
| <LanguageAlternate pythonContent={<a href="./reach-person"><code>on_reach_person</code></a>} typescriptContent={<a href="./reach-person"><code>onReachPerson</code></a>} /> | Called when a <LanguageAlternate pythonContent={<code>reach_person</code>} typescriptContent={<code>reachPerson</code>} /> task completes. |
| <LanguageAlternate pythonContent={<code>on_outbound_failed</code>} typescriptContent={<code>onOutboundFailed</code>} /> | Called when an outbound call fails to dial. |
| <LanguageAlternate pythonContent={<a href="./on-escalate"><code>on_escalate</code></a>} typescriptContent={<a href="./on-escalate"><code>onEscalate</code></a>} /> | Called when an escalation is triggered. Read <LanguageAlternate pythonContent={<code>event.requested_by</code>} typescriptContent={<code>event.requestedBy</code>} /> (<code>'human'</code> or <code>'agent'</code>) to determine which party requested the escalation. |
| <LanguageAlternate pythonContent={<a href="./on-caller-dtmf"><code>on_caller_dtmf</code></a>} typescriptContent={<a href="./on-caller-dtmf"><code>onCallerDtmf</code></a>} /> | Called when the caller presses a keypad key (DTMF). Previously named <LanguageAlternate pythonContent={<code>on_dtmf</code>} typescriptContent={<code>onDtmf</code>} />, which still works. |
| <LanguageAlternate pythonContent={<a href="./on-agent-dtmf"><code>on_agent_dtmf</code></a>} typescriptContent={<a href="./on-agent-dtmf"><code>onAgentDtmf</code></a>} /> | Called when the agent presses keypad keys (DTMF). Read <code>event.requested_by</code> (<code>'agent'</code> or <code>'developer'</code>) to tell an agentic press from one you asked for. |

### Entrypoints / Channels

Attach the agent to a channel to start receiving calls.

| Entrypoint | Description |
|------------|-------------|
| <LanguageAlternate pythonContent={<code>listen_phone("+1...")</code>} typescriptContent={<code>listenPhone("+1...")</code>} /> | Listen for inbound phone calls on the given phone number. |
| <LanguageAlternate pythonContent={<code>listen_webrtc(code?)</code>} typescriptContent={<code>listenWebrtc(code?)</code>} /> | Listen for inbound WebRTC connections to the given agent code. If not provided, a temporary agent code is automatically created. |
| <LanguageAlternate pythonContent={<code>listen_sip("guavasip-...")</code>} typescriptContent={<code>listenSip("guavasip-...")</code>} /> | Listen for inbound SIP connections to the given SIP code. |
| <LanguageAlternate pythonContent={<code>call_phone(from_number, to_number, variables?)</code>} typescriptContent={<code>callPhone(from_number, to_number, variables?)</code>} /> | Place a single outbound phone call. |
| <LanguageAlternate pythonContent={<code>call_local()</code>} typescriptContent={<code>callLocal()</code>} /> | Call the agent using your local audio device (for testing). |
| <LanguageAlternate pythonContent={<code>attach_campaign(campaign)</code>} typescriptContent={<code>attachCampaign(campaign)</code>} /> | Attach an agent to an outbound [Campaign](./campaign). |
| <code>chat(variables?)</code> | Start an interactive terminal chat session with the agent (for testing). |
| <code>test(variables?)</code> | Starts a live test session for programmatic testing. |
| <LanguageAlternate pythonContent={<code>roleplay(roleplay_prompt, variables?)</code>} typescriptContent={<code>roleplay(roleplayPrompt, variables?)</code>} /> | Run an automated test where an LLM roleplays as the caller. |

<Callout>
  To attach an agent to multiple channels, or run multiple agents in the same process, use <a href="/docs/runner">guava.Runner</a>.
</Callout>

<AutoNextLink currentSection="agent" />


---

<!-- section: tasks -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const SET_TASK_SIG_PY = `call.set_task(
    # Unique identifier for this task, used to bind on_task_complete handlers.
    task_id: str,

    # High-level goal for the agent. Provides context when no checklist is given,
    # or alongside a checklist to frame the overall objective.
    objective: str = "",

    # Ordered list of items for the agent to complete during the call.
    checklist: list[Field | Say | str] | None = None,

    # Optional extra guidance on when to consider this task done. Useful for
    # open-ended tasks where the checklist alone doesn't define completion.
    completion_criteria: str = "",
)`;

export const SET_TASK_SIG_TS = `await call.setTask({
  // Unique identifier for this task, used to bind onTaskComplete handlers.
  taskId: string,

  // High-level goal for the agent. Provides context when no checklist is given,
  // or alongside a checklist to frame the overall objective.
  objective?: string,

  // Ordered list of items for the agent to complete during the call.
  checklist?: (FieldItem | SayItem | string)[],

  // Optional extra guidance on when to consider this task done. Useful for
  // open-ended tasks where the checklist alone doesn't define completion.
  completionCriteria?: string,
})`;

## Task

A task is the unit of work your agent completes on a call. Call `call.set_task()` to direct the agent toward a new goal. You can invoke `call.set_task()` on one of your handler callbacks, or at any time (even on another thread).

<CodeTabs
  python={{ code: SET_TASK_SIG_PY, filename: "signature" }}
  typescript={{ code: SET_TASK_SIG_TS, filename: "signature" }}
/>

### Checklist items

The checklist drives the agent forward. Each item is one of three types:

| Type | Purpose |
|------|---------|
| `guava.Field` | Collect structured data from the caller |
| `guava.Say` | Speak a verbatim statement |
| `str` | Natural language instruction for the agent |

<Callout>
  <span className="text-primary font-semibold">guava.Say</span> A <code>guava.Say</code> step is spoken verbatim — use it sparingly when exact wording matters.
</Callout>

### Example

export const SET_TASK_EX_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_task(
        "waitlist",
        objective="You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text", description="Name for the waitlist"),
            guava.Field(key="party_size", field_type="integer", description="Number of people"),
            guava.Field(
                key="phone_number",
                field_type="text",
                description="Phone number to text when the table is ready",
            ),
            "Read the phone number back to the caller to confirm.",
        ],
    )

@agent.on_task_complete("waitlist")
def on_waitlist_done(call: guava.Call):
    logger.info("Added %s, party of %d, to waitlist.",
        call.get_field("caller_name"), call.get_field("party_size"))
    call.hangup("Thank the caller and let them know we'll text when their table is ready.")`;

export const SET_TASK_EX_TS = `agent.onCallStart(async (call) => {
  await call.setTask({
    taskId: "waitlist",
    objective: "You are a virtual assistant for Thai Palace. Add callers to the waitlist.",
    checklist: [
      guava.Field({ key: "caller_name", fieldType: "text", description: "Name for the waitlist" }),
      guava.Field({ key: "party_size", fieldType: "integer", description: "Number of people" }),
      guava.Field({
        key: "phone_number",
        fieldType: "text",
        description: "Phone number to text when the table is ready",
      }),
      "Read the phone number back to the caller to confirm.",
    ],
  });
});

agent.onTaskComplete("waitlist", async (call) => {
  logger.info("Added %s, party of %d, to waitlist.",
    await call.getField("caller_name"), await call.getField("party_size"));
  await call.hangup("Thank the caller and let them know we'll text when their table is ready.");
});`;

<CodeTabs
  python={{ code: SET_TASK_EX_PY, filename: "example.py" }}
  typescript={{ code: SET_TASK_EX_TS, filename: "example.ts" }}
/>

<AutoNextLink currentSection="tasks" />


---

<!-- section: field -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';


export const FIELD_SIG_PY = `guava.Field(
    # Identifier used to retrieve the value via get_field() after collection.
    key: str,

    # Natural-language instruction to the LLM about how to collect this value.
    # Use when you do not particularly care how the agent phrases its question.
    description: str = '',

    # Encourages the agent to ask for the field in a particular way. Use instead
    # of description when you want more control over the phrasing.
    question: str = '',

    # Controls parsing and validation. "calendar_slot" and "multiple_choice"
    # require either choices or searchable=True.
    field_type: Literal[
        'text', 'date', 'datetime', 'integer', 'multiple_choice', 'calendar_slot',
        'digit_sequence', 'cvv'
    ] = 'text',

    # If False, the agent can skip this field if the caller is unwilling to provide it.
    required: bool = True,

    # Static list of valid options for "calendar_slot" and "multiple_choice" fields.
    # Use when the list is small. Large lists should use searchable=True.
    choices: list[str] = [],

    # When True, enables dynamic search for "multiple_choice" and "calendar_slot"
    # fields. The agent searches for options matching the caller's query at runtime.
    searchable: bool = False,

    # When True, the collected value is treated as sensitive: it is redacted from
    # stored transcripts and call recordings. See "Sensitive Fields" below. The "cvv"
    # field type is always sensitive and additionally suppresses logs and diagnostic data.
    sensitive: bool = False,
)`;

export const FIELD_SIG_TS = `guava.Field({
  // Identifier used to retrieve the value via get_field() after collection.
  key: string,

  // Natural-language instruction to the LLM about how to collect this value.
  // Use when you do not particularly care how the agent phrases its question.
  description?: string,

  // Encourages the agent to ask for the field in a particular way. Use instead
  // of description when you want more control over the phrasing.
  question?: string,

  // Controls parsing and validation. "calendar_slot" and "multiple_choice"
  // require either choices or choiceGenerator.
  fieldType:
    'text' | 'date' | 'datetime' | 'integer' | 'multiple_choice' | 'calendar_slot' |
    'digit_sequence' | 'cvv',

  // If false, the agent can skip this field if the caller is unwilling to provide it.
  required?: boolean, // default: true

  // Static list of valid options for "calendar_slot" and "multiple_choice" fields.
  // Use when the list is small. Large lists should use choiceGenerator.
  choices?: string[], // default: []

  // Takes a query string and returns (matching, fallback) lists. Use for large
  // or dynamic option sets with "calendar_slot" and "multiple_choice".
  choiceGenerator?: ChoiceGenerator,

  // When true, enables dynamic search for "multiple_choice" and "calendar_slot"
  // fields. The agent searches for options matching the caller's query at runtime.
  searchable?: boolean, // default: false

  // When true, the collected value is treated as sensitive: it is redacted from
  // stored transcripts and call recordings. See "Sensitive Fields" below. The "cvv"
  // field type is always sensitive and additionally suppresses logs and diagnostic data.
  sensitive?: boolean, // default: false
})`;

## Field

A `Field` is a [Task](./tasks) checklist item instructing the Guava agent to collect structured data from the caller. The agent elicits the value through natural conversation, validates it against the specified type, and marks the checklist item complete when satisfied.


<CodeTabs
  python={{ code: FIELD_SIG_PY, filename: "signature" }}
  typescript={{ code: FIELD_SIG_TS, filename: "signature" }}
/>


### Basic Examples

export const FIELD_EX1_PY = `# Basic text field
field = guava.Field(
    key="caller_name",
    description="Get the caller's name",
)

# Integer field with question
field = guava.Field(
    key="caller_age",
    question="How old are you?",
    field_type="integer",
)

# Multiple choice with static choices
field = guava.Field(
    key="caller_preference",
    description="Get the caller's preferred fruit",
    field_type="multiple_choice",
    # Use searchable=True instead when there's a large number of choices
    choices=["apple", "banana", "orange"],
    required=False,
)`;

export const FIELD_EX1_TS = `// Basic text field
const field = guava.Field({
  key: "caller_name",
  description: "Get the caller's name",
});

// Integer field with question
const field = guava.Field({
  key: "caller_age",
  question: "How old are you?",
  fieldType: "integer",
});

// Multiple choice with static choices
const field = guava.Field({
  key: "caller_preference",
  description: "Get the caller's preferred fruit",
  fieldType: "multiple_choice",
  // Use searchable: true instead when there's a large number of choices
  choices: ["apple", "banana", "orange"],
  required: false,
});`;

<CodeTabs
  python={{ code: FIELD_EX1_PY, filename: "examples.py" }}
  typescript={{ code: FIELD_EX1_TS, filename: "examples.ts" }}
/>

### Search Fields

Some fields can have a very large set of valid options.
For example, a `destination_airport` field may include thousands of airports worldwide.
In other cases, options must be generated dynamically, such as an `appointment_time` field populated from a booking system.

This is where search fields come in handy. Set `searchable=True` on the field, then register an `@agent.on_search_query` handler.
When the agent needs options, it calls your handler with a natural-language query string.
Return two lists: a primary list of matches, and a fallback list shown only when no primary matches are found.

export const FIELD_EX4_PY = `field = guava.Field(
    key="airport",
    description="Find a suitable airport for the caller",
    field_type="multiple_choice",
    searchable=True,
)

@agent.on_search_query("airport")
def search_airports(call: guava.Call, query: str):
    matching_airports: list[str] = []
    other_airports: list[str] = []

    ...
    # Do some work to generate a few matching airport
    # options based on the caller's query.
    # 'query' will be human natural language
    # (e.g. "I need to fly out of an airport in
    # southern california")
    ...

    # The second list only becomes relevant if there
    # are no matches to the caller's query. It is used
    # to at least present something to the caller in
    # case there are no perfect matches.
    return matching_airports, other_airports`;

export const FIELD_EX4_TS = `const field = guava.Field({
  key: "airport",
  description: "Find a suitable airport for the caller",
  fieldType: "multiple_choice",
  searchable: true,
});

agent.onSearchQuery("airport", async (call, query) => {
  const matchingAirports: string[] = [];
  const otherAirports: string[] = [];

  // ...
  // Do some work to generate a few matching airport
  // options based on the caller's query.
  // 'query' will be human natural language
  // (e.g. "I need to fly out of an airport in
  // southern california")
  // ...

  // The second list only becomes relevant if there
  // are no matches to the caller's query. It is used
  // to at least present something to the caller in
  // case there are no perfect matches.
  return [matchingAirports, otherAirports];
})`;

<CodeTabs
  python={{ code: FIELD_EX4_PY, filename: "search_field.py" }}
  typescript={{ code: FIELD_EX4_TS, filename: "search_field.ts" }}
/>

### Sensitive Fields

Some fields collect information that should never persist in plain form — Social Security numbers, dates of birth, health details, account credentials, or payment data.
Mark any field as sensitive by setting `sensitive=True`. When a sensitive field is present on a call, Guava applies the following protections to the collected value:

- **Transcript redaction.** The value is removed from stored transcripts, matching both spoken and written forms (e.g. "one two three" as well as "123").
- **Audio redaction.** The corresponding region of the call recording is silenced across all channels.

`sensitive` is a general-purpose flag — use it for any field whose value your organization considers sensitive.

<Callout>
  <span className="text-primary font-semibold">Important:</span> The <code>sensitive</code> flag redacts the value from stored transcripts and recordings, but it does <strong>not</strong> guarantee the value is kept out of diagnostic and debug data. For payment card data, use the <code>cvv</code> field type (see below), which additionally suppresses logging and diagnostic capture for the entire session.
</Callout>

export const FIELD_EX_SENSITIVE_PY = `# Mark any field as sensitive to redact its collected value
ssn = guava.Field(
    key="ssn",
    question="What are the last four digits of your Social Security number?",
    field_type="digit_sequence",
    sensitive=True,
)`;

export const FIELD_EX_SENSITIVE_TS = `// Mark any field as sensitive to redact its collected value
const ssn = guava.Field({
  key: "ssn",
  question: "What are the last four digits of your Social Security number?",
  fieldType: "digit_sequence",
  sensitive: true,
});`;

<CodeTabs
  python={{ code: FIELD_EX_SENSITIVE_PY, filename: "sensitive_field.py" }}
  typescript={{ code: FIELD_EX_SENSITIVE_TS, filename: "sensitive_field.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Note:</span> Redaction is applied on a best-effort basis to spoken conversation. Mark every field that may capture sensitive information, and choose the most specific `field_type` available (for example, `digit_sequence` for account or ID numbers) to give the agent the clearest signal.
</Callout>

#### Payment Data (PCI)

For payment card collection, use the dedicated `cvv` field type. Fields of this type are **always** treated as sensitive — you do not need to set `sensitive=True` explicitly — and receive the transcript and audio redaction described above.

Unlike a field that is merely marked `sensitive`, the `cvv` field type provides two additional protections that apply to the entire session:

- **Log exclusion.** The value is kept out of application logs; only the field name is logged, never the collected value.
- **Diagnostic data suppression.** All diagnostic and debug data for the session is suppressed and not retained, and any diagnostic data already written is discarded.

These stronger, session-wide protections are specific to the `cvv` field type.

export const FIELD_EX_PCI_PY = `# The "cvv" field type is automatically sensitive
card_number = guava.Field(
    key="card_number",
    question="What is your card number?",
    field_type="digit_sequence",
    sensitive=True,
)

cvv = guava.Field(
    key="cvv",
    question="And the three-digit security code on the back?",
    field_type="cvv",
    # sensitive=True is implied by the "cvv" field type
)`;

export const FIELD_EX_PCI_TS = `// The "cvv" field type is automatically sensitive
const cardNumber = guava.Field({
  key: "card_number",
  question: "What is your card number?",
  fieldType: "digit_sequence",
  sensitive: true,
});

const cvv = guava.Field({
  key: "cvv",
  question: "And the three-digit security code on the back?",
  fieldType: "cvv",
  // sensitive: true is implied by the "cvv" field type
});`;

<CodeTabs
  python={{ code: FIELD_EX_PCI_PY, filename: "payment_field.py" }}
  typescript={{ code: FIELD_EX_PCI_TS, filename: "payment_field.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Note:</span> Card numbers are not automatically sensitive. When collecting a full card number, use a `digit_sequence` field with `sensitive=True`, as shown above.
</Callout>

### Field Types Reference

| Type | Example collected value | Return type from `get_field()` |
|------|------------------------|-------------------------------|
| `text` | `"I want to cancel my appointment"` | `str` |
| `date` | `{"year": 2024, "month": 3, "day": 15}` | `dict` with keys `year`, `month`, `day` (all `int`) |
| `integer` | `42` | `int` |
| `multiple_choice` | `"apple"` | `str` (guaranteed to be one of `choices` or returned by `choice_generator`) |
| `calendar_slot` | `"2022-12-31T17:30"` | ISO-8601 datetime `str` |
| `digit_sequence` | `"1234"` | `str` (digits only; useful for account, ID, or card numbers) |
| `cvv` | `"123"` | `str` (always sensitive; redacted from transcripts, audio, and logs) |

<Callout>
  <span className="text-primary font-semibold">Note:</span> The `choices` list for `calendar_slot` fields must be ISO-8601 datetimes (e.g. `"2022-12-31T17:30"`).
</Callout>

<AutoNextLink currentSection="field" />


---

<!-- section: runner -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { CodeTabs, LanguageTabs } from '../views/docs/CodeTabs';
import { PropTable, AutoNextLink } from '../views/docs/prose';

export const RUNNER_EX_PY = `import os
from guava import Agent, Runner

agent_a = Agent(name="Grace", purpose="You are a helpful voice agent.")
agent_b = Agent(name="Jordan", purpose="You are a helpful voice agent.")

runner = Runner()
runner.listen_phone(agent_a, os.environ["GUAVA_AGENT_NUMBER"])
runner.listen_webrtc(agent_b)
runner.run()`;

export const RUNNER_EX_TS = `import * as guava from "@guava-ai/guava-sdk";

const agentA = new guava.Agent({ name: "Grace", purpose: "You are a helpful voice agent." });
const agentB = new guava.Agent({ name: "Jordan", purpose: "You are a helpful voice agent." });

const runner = new guava.Runner();
runner.listenPhone(agentA, process.env.GUAVA_AGENT_NUMBER!);
runner.listenWebrtc(agentB);
await runner.run();`;

## Runner

`guava.Runner` lets you serve multiple agents in a single process. Each agent can be attached to any number of channels — phone, WebRTC, SIP, or outbound campaigns. Call `run()` to start everything and block until all channels exit.

<CodeTabs
  python={{ code: RUNNER_EX_PY, filename: "run.py" }}
  typescript={{ code: RUNNER_EX_TS, filename: "run.ts" }}
/>

### Methods

<LanguageTabs
  pythonContent={<PropTable rows={[
    { name: "listen_phone(agent, agent_number)", type: "Runner", desc: "Register an agent to receive inbound calls on the given phone number. Returns self for chaining." },
    { name: "listen_webrtc(agent, webrtc_code?)", type: "Runner", desc: "Register an agent to accept WebRTC connections. A new code is generated if the code is omitted. Returns self for chaining." },
    { name: "listen_sip(agent, sip_code)", type: "Runner", desc: "Register an agent to receive inbound SIP calls on the given SIP code. Returns self for chaining." },
    { name: "attach_campaign(agent, campaign)", type: "Runner", desc: "Attach an outbound campaign to an agent. Returns self for chaining." },
    { name: "run()", type: "None", desc: "Start all registered channels and block until they all exit." },
  ]} />}
  typescriptContent={<PropTable rows={[
    { name: "listenPhone(agent, agentNumber)", type: "Runner", desc: "Register an agent to receive inbound calls on the given phone number. Returns self for chaining." },
    { name: "listenWebrtc(agent, webrtcCode?)", type: "Runner", desc: "Register an agent to accept WebRTC connections. A new code is generated if the code is omitted. Returns self for chaining." },
    { name: "listenSip(agent, sipCode)", type: "Runner", desc: "Register an agent to receive inbound SIP calls on the given SIP code. Returns self for chaining." },
    { name: "attachCampaign(agent, campaignCode)", type: "Runner", desc: "Attach an outbound campaign to an agent. Returns self for chaining." },
    { name: "run()", type: "Promise<void>", desc: "Start all registered channels and block until they all exit." },
  ]} />}
/>

<AutoNextLink currentSection="runner" />


---

<!-- section: client -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { PropTable, AutoNextLink } from '../views/docs/prose';

export const CLIENT_EX_PY = `import guava, os

client = guava.Client(
    api_key=os.environ["GUAVA_API_KEY"],   # or omit — reads env automatically
)`;

export const CLIENT_EX_TS = `import * as guava from "@guava-ai/guava-sdk";

const client = new guava.Client(
  process.env.GUAVA_API_KEY,  // or omit — reads env automatically
);`;

## Client

`guava.Client` complements [`guava.Agent`](./agent) by providing functions for managing account-level resources. It also provides any functions that don't fit onto [`guava.Agent`](./agent).

<CodeTabs
  python={{ code: CLIENT_EX_PY, filename: "run.py" }}
  typescript={{ code: CLIENT_EX_TS, filename: "run.ts" }}
/>

### API

<PropTable rows={[
  { name: "api_key", type: "str | None", default: "env GUAVA_API_KEY", desc: "Your Guava API key." },
  { name: "base_url", type: "str | None", default: "production", desc: "Override the API endpoint (for testing)." },
]} />

### Methods

<PropTable rows={[
  { name: "create_sip_agent()", type: "method", desc: "Generate a SIP code linked to your account for inbound SIP call handling." },
  { name: "create_webrtc_agent(ttl)", type: "method", desc: "Generate a WebRTC code for browser-based voice interaction, with optional TTL." },
  { name: "send_sms()", type: "method", desc: "Send an SMS message. See SMS Messaging." },
  { name: "next_sms()", type: "method", desc: "Wait for and return the next inbound SMS reply. See SMS Messaging." },
]} />

See [SMS Messaging](./messaging) for details on `send_sms` and `next_sms`.

<AutoNextLink currentSection="client" />


---

<!-- section: messaging -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { PropTable, Callout, AutoNextLink } from '../views/docs/prose';

export const SMS_EX_PY = `import guava
import os

client = guava.Client(api_key=os.environ["GUAVA_API_KEY"])

agent_number = os.environ["GUAVA_AGENT_NUMBER"]   # one of your Guava numbers
customer = "+15551234567"

# Send an SMS from your Guava number to the customer.
client.send_sms(
    from_number=agent_number,
    to_number=customer,
    message="Hi! Reply YES to confirm your appointment, or STOP to opt out.",
)

# Block until the customer replies, giving up after 5 minutes.
reply = client.next_sms(from_number=customer, to_number=agent_number, timeout=300)

if reply is None:
    print("No reply within 5 minutes.")
else:
    print("Customer replied:", reply["content"])`;

export const SMS_EX_TS = `import * as guava from "@guava-ai/guava-sdk";

const client = new guava.Client(process.env.GUAVA_API_KEY);

const agentNumber = process.env.GUAVA_AGENT_NUMBER;  // one of your Guava numbers
const customer = "+15551234567";

// Send an SMS from your Guava number to the customer.
await client.sendSms(
  agentNumber,
  customer,
  "Hi! Reply YES to confirm your appointment, or STOP to opt out.",
);

// Block until the customer replies, giving up after 5 minutes.
const reply = await client.nextSms(customer, agentNumber, { timeoutMs: 300_000 });

if (reply === null) {
  console.log("No reply within 5 minutes.");
} else {
  console.log("Customer replied:", reply.content);
}`;

export const SMS_SEND_SIG_PY = `client.send_sms(
    from_number: str,
    to_number: str,
    message: str,
) -> None`;

export const SMS_SEND_SIG_TS = `await client.sendSms(
  fromNumber: string,
  toNumber: string,
  message: string,
): Promise<void>`;

export const SMS_NEXT_SIG_PY = `client.next_sms(
    from_number: str,
    to_number: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 2.0,
) -> dict | None`;

export const SMS_NEXT_SIG_TS = `await client.nextSms(
  fromNumber: string,
  toNumber: string,
  options?: { timeoutMs?: number; pollIntervalMs?: number },
): Promise<SmsMessage | null>`;

## SMS Messaging

The [`guava.Client`](./client) can send SMS messages from your Guava numbers and wait for inbound replies. This is useful for sending confirmations and reminders, or for collecting a response between calls.

<Callout>
  SMS messaging is available in the <strong>Python and TypeScript SDKs</strong>. For other languages, call the equivalent <a href="/docs/messages-api">Messages REST API</a> directly.
</Callout>

<CodeTabs
  python={{ code: SMS_EX_PY, filename: "sms.py" }}
  typescript={{ code: SMS_EX_TS, filename: "sms.ts" }}
/>

### send_sms / sendSms

Send a single SMS message. The `from_number` must be one of your Guava numbers with SMS configured, and the message is delivered to `to_number`.

<CodeTabs
  python={{ code: SMS_SEND_SIG_PY, filename: "signature" }}
  typescript={{ code: SMS_SEND_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  { name: "from_number", type: "str", desc: "One of your Guava numbers, in E.164 format (e.g. \"+15551230001\"). Must have SMS enabled." },
  { name: "to_number", type: "str", desc: "The recipient's number, in E.164 format." },
  { name: "message", type: "str", desc: "The message body to send." },
]} />

Returns nothing (Python `None`; TypeScript resolves `void`). Raises (Python) / rejects (TypeScript) if the `from_number` isn't owned by your organization or doesn't have SMS configured.

<Callout>
  Sending SMS requires your organization to complete SMS brand and campaign registration. See <a href="/docs/outbound-and-sms-permissions">Outbound &amp; SMS Compliance</a>.
</Callout>

### next_sms / nextSms

Wait for the next inbound SMS sent **to** one of your Guava numbers **from** a given number, and return it. `next_sms` polls your inbox and only returns messages received after the call begins, so a reply to an earlier message won't be returned twice.

<Callout>
  Note the direction: `from_number` is the external number you're waiting to hear from (the customer), and `to_number` is your Guava number that receives the reply — the opposite of <code>send_sms</code>.
</Callout>

<CodeTabs
  python={{ code: SMS_NEXT_SIG_PY, filename: "signature" }}
  typescript={{ code: SMS_NEXT_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  { name: "from_number", type: "str", desc: "The external number you're waiting to hear from, in E.164 format." },
  { name: "to_number", type: "str", desc: "Your Guava number that will receive the reply, in E.164 format." },
  { name: "timeout", type: "float", default: "60.0", desc: "Maximum number of seconds to wait before giving up. In TypeScript, pass `timeoutMs` (milliseconds) in the options object; defaults to 60000." },
  { name: "poll_interval", type: "float", default: "2.0", desc: "Seconds to wait between inbox checks. In TypeScript, pass `pollIntervalMs` (milliseconds) in the options object; defaults to 2000." },
]} />

Returns the message (Python `dict` / TypeScript `SmsMessage`), or `None` / `null` if the timeout elapses with no new message. A message has the following fields:

<PropTable rows={[
  { name: "id", type: "str", desc: "Unique ID of the message." },
  { name: "from_number", type: "str", desc: "The number that sent the message." },
  { name: "to_number", type: "str", desc: "Your Guava number that received the message." },
  { name: "content", type: "str", desc: "The message body." },
  { name: "received_at", type: "str", desc: "When the message was received, in ISO 8601 format." },
  { name: "modality", type: "str", desc: "The channel the message arrived on. Currently always \"sms\"." },
  { name: "direction", type: "str", desc: "Always \"inbound\" for received messages." },
]} />

<AutoNextLink currentSection="messaging" />


---

<!-- section: on-question -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { AutoNextLink } from '../views/docs/prose';

export const ON_QUESTION_SIG_PY = `@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    # question: natural-language question from the caller
    # return: answer to relay to caller
    ...`;

export const ON_QUESTION_SIG_TS = `agent.onQuestion(async (call: guava.Call, question: string) => string);`;

export const ON_QUESTION_EX_PY = `import guava
from guava import Agent
from guava.helpers.rag import DocumentQA
from guava.examples.example_data import PROPERTY_INSURANCE_POLICY

agent = Agent(
    organization="Harper Valley Property Insurance",
    purpose="Answer questions regarding property insurance policy",
)

document_qa = DocumentQA(documents=PROPERTY_INSURANCE_POLICY)

@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    return document_qa.ask(question)`;

export const ON_QUESTION_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { DocumentQA } from "@guava-ai/guava-sdk/helpers";
import { PROPERTY_INSURANCE_POLICY } from "@guava-ai/guava-sdk/example-data";

const agent = new guava.Agent({
  organization: "Harper Valley Property Insurance",
  purpose: "Answer questions regarding property insurance policy",
});

const documentQA = new DocumentQA({
  documents: PROPERTY_INSURANCE_POLICY,
  namespace: "harper-valley-property-insurance",
});

agent.onQuestion(async (call: guava.Call, question: string) => {
  return await documentQA.ask(question);
});`;

## on\_question()

When a Guava agent is asked a question that it cannot answer from its context alone, it will invoke the `on_question` callback. Your **Expert** then has the chance to answer that question, typically using a RAG system. Our examples use the provided `DocumentQA` class, but you can use any RAG system you prefer.

See our [Q&A example](./inbound-rag-example) for a step-by-step walkthrough.

<CodeTabs
  python={{ code: ON_QUESTION_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_QUESTION_SIG_TS, filename: "signature" }}
/>

> If you want the agent to answer questions immediately, use `add_info` to pre-emptively add information to the context.

- `on_question`, like all Guava callbacks, is invoked asynchronously and does not block dialog. The Guava voice agent continues to engage the caller until the question answer comes back.
- `on_question` may be invoked multiple times, for example, if a caller asks a question and then refines it. `on_question` may be invoked speculatively before a caller is done talking.
- `on_question` may be invoked simultaneously with [`on_action_request`](./on-action-request-execute), as some requests can be both an "action" and a "question". For example, *"Do you have a lost and found?"* In this case, the agent will synthesize both responses: *"Yes, we have a lost and found. Would you like me to transfer you there?"*



### Example

<CodeTabs
  python={{ code: ON_QUESTION_EX_PY, filename: "support_controller.py" }}
  typescript={{ code: ON_QUESTION_EX_TS, filename: "support_controller.ts" }}
/>

<AutoNextLink currentSection="on-question" />


---

<!-- section: on-action-request-execute -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';

export const ON_ACTION_REQUEST_SIG_PY = `@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction | None:
    # request: natural-language summary of what the caller wants
    # return: SuggestedAction(key=...) or None

@agent.on_action("action_key")
def handler(call: guava.Call) -> None:
    # Runs when Guava executes the action with the matching key
    ...`;

export const ON_ACTION_REQUEST_SIG_TS = `agent.onActionRequest(
  async (call: guava.Call, request: string) => { key: string } | null
);

agent.onAction("action_key", async (call: guava.Call) => {
  // Runs when Guava executes the action with the matching key
});`;

export const ON_ACTION_REQUEST_EX_PY = `from guava import Agent, SuggestedAction
from guava.helpers.llm import IntentRecognizer

agent = Agent(name="Nova", organization="Thai Palace", purpose="...")

ACTIONS = {
    "reservation": "for handling reservations",
    "waitlist": "additions to the waitlist",
    "delivery": "for takeout orders",
    "hiring": "for people looking for jobs",
    "order_for_pickup": "",
}

intent_recognizer = IntentRecognizer(ACTIONS)


@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction | None:
    key = intent_recognizer.classify(request)
    return SuggestedAction(key=key) if key else None


@agent.on_action("reservation")
def reservation(call: guava.Call):
    call.set_task(...)


@agent.on_action("waitlist")
def waitlist(call: guava.Call):
    call.set_task(...)`;

export const ON_ACTION_REQUEST_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { IntentRecognizer } from "@guava-ai/guava-sdk/helpers";

const agent = new guava.Agent({
  name: "Nova",
  organization: "Thai Palace",
  purpose: "...",
});

const ACTIONS = {
  reservation: "for handling reservations",
  waitlist: "additions to the waitlist",
  delivery: "for takeout orders",
  hiring: "for people looking for jobs",
  order_for_pickup: "",
};

const intentRecognizer = new IntentRecognizer(Object.keys(ACTIONS));

agent.onActionRequest(async (_call: guava.Call, request: string) => {
  const key = await intentRecognizer.classify(request);
  return key ? { key } : null;
});

agent.onAction("reservation", async (call: guava.Call) => {
  call.setTask({ objective: "Handle reservation" });
});

agent.onAction("waitlist", async (call: guava.Call) => {
  call.setTask({ objective: "Handle waitlist addition" });
});`;


## on\_action\_request() / on\_action()

These handlers are used when the caller expresses an intent or action (e.g. "I'd like to pay my bill"). The flow is as follows.

1. **The caller makes a request** — e.g. "I'd like to check the status of my order."
2. **Guava invokes `on_action_request` with a summary of the request** — e.g. "the customer would like to check the status of their order."
3. **You classify the request and return a `SuggestedAction`** — e.g. `SuggestedAction(key="order_status")`. You can use our built-in `IntentRecognizer` helper, or build your own intent classifier. Return `None` if no action matches the request.
4. **Guava decides whether to execute the action** — it may proceed immediately or ask the caller to confirm.
5. **Guava executes the action** — The `on_action` handler registered under the matching suggested action key is called.

<Callout>
  <span className="text-primary font-semibold">Design note:</span> The two-step pattern (request → execute) gives the agent a chance to confirm intent with the caller before committing to an action.
</Callout>

<CodeTabs
  python={{ code: ON_ACTION_REQUEST_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_ACTION_REQUEST_SIG_TS, filename: "signature" }}
/>

### Interaction with on\_question

A caller utterance can be both a question and an action (e.g. *"Could you help me pay my bill?"*). In this case Guava will invoke both callbacks in parallel and synthesize an appropriate response based on the results.

For example, if `on_question` returns *"Yes, we handle bill payment"* and `on_action_request` returns `SuggestedAction(key="bill_pay")`,
Guava may immediately chain into executing the action, or it may respond *"Yes — would you like to get started?"* to confirm the action with the caller.

### Example

<CodeTabs
  python={{ code: ON_ACTION_REQUEST_EX_PY, filename: "restaurant_controller.py" }}
  typescript={{ code: ON_ACTION_REQUEST_EX_TS, filename: "restaurant_controller.ts" }}
/>

<AutoNextLink currentSection="on-action-request-execute" />


---

<!-- section: on-task-complete -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const ON_TASK_COMPLETE_SIG_PY = `# Per-task form (recommended)
@agent.on_task_complete("task_name")
def handler(call: guava.Call) -> None:
    ...

# Generic form — fires for all tasks
@agent.on_task_complete
def handler(call: guava.Call, task_id: str) -> None:
    ...`;

export const ON_TASK_COMPLETE_SIG_TS = `// Per-task form (recommended)
agent.onTaskComplete("task_name", async (call: guava.Call) => void);

// Generic form — fires for all tasks
agent.onTaskComplete(async (call: guava.Call, taskId: string) => void);`;

export const ON_TASK_COMPLETE_EX_PY = `import logging
import guava
from guava import Agent

logger = logging.getLogger(__name__)

agent = Agent(
    organization="Thai Palace",
    purpose="Add callers to the waitlist",
)

@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_task(
        "waitlist",
        objective="Add the caller to the waitlist.",
        checklist=[
            guava.Field(key="caller_name", field_type="text", description="Name for the waitlist"),
            guava.Field(key="party_size", field_type="integer", description="Number of people"),
            guava.Field(key="phone_number", field_type="text", description="Phone number to text when ready"),
            "Read the phone number back to the caller to confirm.",
        ],
    )

@agent.on_task_complete("waitlist")
def on_waitlist_done(call: guava.Call):
    name = call.get_field("caller_name")
    size = call.get_field("party_size")
    logger.info("Added %s, party of %d, to waitlist.", name, size)
    call.hangup("Thank the caller and let them know we'll text when their table is ready.")`;

export const ON_TASK_COMPLETE_EX_TS = `import * as guava from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  organization: "Thai Palace",
  purpose: "Add callers to the waitlist",
});

agent.onCallStart(async (call) => {
  await call.setTask({
    taskId: "waitlist",
    objective: "Add the caller to the waitlist.",
    checklist: [
      guava.Field({ key: "caller_name", fieldType: "text", description: "Name for the waitlist" }),
      guava.Field({ key: "party_size", fieldType: "integer", description: "Number of people" }),
      guava.Field({ key: "phone_number", fieldType: "text", description: "Phone number to text when ready" }),
      "Read the phone number back to the caller to confirm.",
    ],
  });
});

agent.onTaskComplete("waitlist", async (call) => {
  const name = await call.getField("caller_name");
  const size = await call.getField("party_size");
  console.log(\`Added \${name}, party of \${size}, to waitlist.\`);
  await call.hangup("Thank the caller and let them know we'll text when their table is ready.");
});`;

## on\_task\_complete()

`on_task_complete` is called when a [Task](./tasks) previously set with `call.set_task()` is completed by the agent. Use it to persist collected data, trigger downstream workflows, or move the call to the next stage.

### Signature

There are two forms:

<CodeTabs
  python={{ code: ON_TASK_COMPLETE_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_TASK_COMPLETE_SIG_TS, filename: "signature" }}
/>

- **Per-task form** (recommended): `@agent.on_task_complete("task_name")` binds the handler to a specific `task_id`. The handler receives only the `Call` object.
- **Generic form**: `@agent.on_task_complete` (bare decorator) fires for every completed task. The handler receives the `Call` object and the `task_id` string, letting you dispatch on it manually.

<Callout>
  You cannot mix both forms on the same agent — using per-task handlers alongside a generic handler raises a <code>TypeError</code>.
</Callout>

- `on_task_complete` fires once all checklist items are resolved and the agent has signaled completion.
- Use [`call.get_field()`](./get-field) inside the handler to read values collected during the task.
- The call is still live when this handler runs — you can issue commands such as `call.set_task()`, `call.hangup()`, or `call.transfer()`.

### Example

<CodeTabs
  python={{ code: ON_TASK_COMPLETE_EX_PY, filename: "waitlist_controller.py" }}
  typescript={{ code: ON_TASK_COMPLETE_EX_TS, filename: "waitlist_controller.ts" }}
/>

<AutoNextLink currentSection="on-task-complete" />


---

<!-- section: on-caller-dtmf -->

import { CodeTabs, LanguageAlternate } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';

export const ON_CALLER_DTMF_SIG_PY = `@agent.on_caller_dtmf
def on_caller_dtmf(call: guava.Call, event: DTMFPressedEvent) -> None:
    ...`;

export const ON_CALLER_DTMF_SIG_TS = `agent.onCallerDtmf((call: guava.Call, event: DTMFPressedEvent) => Promise<void>);`;

export const ON_CALLER_DTMF_EX_PY = `import logging

from guava.events import DTMFPressedEvent

@agent.on_caller_dtmf
def on_caller_dtmf(call: guava.Call, event: DTMFPressedEvent):
    logging.info("Caller pressed %s (so far: %s)", event.digit, event.recent_digits)`;

export const ON_CALLER_DTMF_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import type { DTMFPressedEvent } from "@guava-ai/guava-sdk";

agent.onCallerDtmf(async (call: guava.Call, event: DTMFPressedEvent) => {
  console.log(\`Caller pressed \${event.digit} (so far: \${event.recent_digits})\`);
});`;


## on\_caller\_dtmf()

Register a handler that fires whenever the **caller** presses a DTMF digit (0–9, \*, #, A–D) on their keypad.

> **Caller keypresses only.** `on_caller_dtmf` fires for digits pressed by the caller. To enable the agent itself to send DTMF tones (e.g. to navigate an IVR system it has called into), use `call.set_agent_dtmf(enabled=True)` instead, and register <a href="/docs/on-agent-dtmf"><code>on_agent_dtmf</code></a> to observe the digits it presses.

<Callout>
  <span className="text-primary font-semibold">Previously <code>on_dtmf</code>:</span> this callback was named <LanguageAlternate pythonContent={<code>on_dtmf</code>} typescriptContent={<code>onDtmf</code>} /> before <code>on_agent_dtmf</code> existed. The old name still registers the same handler and keeps working — it just no longer says which side of the call pressed the keys.
</Callout>

The `DTMFPressedEvent` is a pydantic model imported from `guava.events`:

```python
from guava.events import DTMFPressedEvent

class DTMFPressedEvent(BaseEvent):
    event_type: Literal["dtmf"] = "dtmf"
    digit: Literal["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#", "A", "B", "C", "D"]
    recent_digits: str = ''
```

### Signature

<CodeTabs
  python={{ code: ON_CALLER_DTMF_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_CALLER_DTMF_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The active call object.",
  },
  {
    name: "event",
    type: "DTMFPressedEvent",
    desc: 'Contains `digit` (string): the key the caller pressed — one of "0"–"9", "*", "#", "A", "B", "C", or "D"; and `recent_digits` (string): the digits pressed so far in this run of keypresses, including this one.',
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_CALLER_DTMF_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_CALLER_DTMF_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-caller-dtmf" />


---

<!-- section: on-agent-dtmf -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';

export const ON_AGENT_DTMF_SIG_PY = `@agent.on_agent_dtmf
def on_agent_dtmf(call: guava.Call, event: AgentDTMFSentEvent) -> None:
    ...`;

export const ON_AGENT_DTMF_SIG_TS = `agent.onAgentDtmf((call: guava.Call, event: AgentDTMFSentEvent) => Promise<void>);`;

export const ON_AGENT_DTMF_EX_PY = `import logging

from guava.events import AgentDTMFSentEvent

@agent.on_call_start
def on_call_start(call: guava.Call):
    # Let the agent press digits on its own to work through IVR menus.
    call.set_agent_dtmf(enabled=True)

@agent.on_agent_dtmf
def on_agent_dtmf(call: guava.Call, event: AgentDTMFSentEvent):
    logging.info(
        "Agent pressed %s (requested by %s)",
        "".join(event.digits),
        event.requested_by,
    )`;

export const ON_AGENT_DTMF_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import type { AgentDTMFSentEvent } from "@guava-ai/guava-sdk";

agent.onCallStart(async (call: guava.Call) => {
  // Let the agent press digits on its own to work through IVR menus.
  await call.setAgentDtmf(true);
});

agent.onAgentDtmf(async (call: guava.Call, event: AgentDTMFSentEvent) => {
  console.log(\`Agent pressed \${event.digits.join("")} (requested by \${event.requested_by})\`);
});`;

## on\_agent\_dtmf()

Register a handler that fires whenever the **agent** presses DTMF digits on the keypad.

This callback covers both ways the agent's digits get pressed:

- **Agentic** — the agent decided to press the digits itself, which it can do once you have called `call.set_agent_dtmf(enabled=True)` (e.g. to work through an IVR menu on a call it placed).
- **Developer-requested** — you asked for the digits explicitly with `call.send_dtmf(...)`.

The two are distinguished by `requested_by`, so a single handler can log every tone the agent sends.

<Callout>
  <span className="text-primary font-semibold">Agent keypresses only:</span> for digits pressed by the person on the other end of the call, use <a href="/docs/on-caller-dtmf"><code>on_caller_dtmf</code></a> instead.
</Callout>

The `AgentDTMFSentEvent` is a pydantic model imported from `guava.events`:

```python
from guava.events import AgentDTMFSentEvent

class AgentDTMFSentEvent(BaseEvent):
    event_type: Literal["agent-dtmf"] = "agent-dtmf"
    digits: list[Literal["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#", "A", "B", "C", "D"]]
    requested_by: Literal["agent", "developer"] = "agent"
```

<Callout>
  <span className="text-primary font-semibold">Digits are reported, not confirmed:</span> the event fires when the agent sends the tones, which is the same moment the digits are handed to the carrier. It is not an acknowledgement that the far end registered them.
</Callout>

### Signature

<CodeTabs
  python={{ code: ON_AGENT_DTMF_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_AGENT_DTMF_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The active call object.",
  },
  {
    name: "event",
    type: "AgentDTMFSentEvent",
    desc: 'Contains `digits` (list of strings): the keys the agent pressed, in order; and `requested_by` (string): `\'agent\'` if the agent chose to press them, `\'developer\'` if they came from `send_dtmf()`.',
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_AGENT_DTMF_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_AGENT_DTMF_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-agent-dtmf" />


---

<!-- section: on-session-end -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';

export const ON_SESSION_END_SIG_PY = `@agent.on_session_end
def on_session_end(call: guava.Call, event: BotSessionEnded) -> None:
    ...`;

export const ON_SESSION_END_SIG_TS = `agent.onSessionEnd(async (call: guava.Call, event: BotSessionEnded) => void);`;

export const ON_SESSION_END_EX_PY = `import logging
from guava.events import BotSessionEnded

logger = logging.getLogger(__name__)


@agent.on_session_end
def on_session_end(call: guava.Call, event: BotSessionEnded):
    logger.info("session ended: reason=%s", event.termination_reason)

    if event.dnc:
        # caller verbally opted out — number added to org DNC list
        logger.info("Contact opted out, added to DNC list.")

    if event.termination_reason == "user-hangup":
        # caller hung up — save any collected data
        ...
    elif event.termination_reason == "bot-transfer":
        # call was transferred to a human agent
        ...`;

export const ON_SESSION_END_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import type { BotSessionEnded } from "@guava-ai/guava-sdk";

agent.onSessionEnd(async (_call: guava.Call, event: BotSessionEnded) => {
  console.log("session ended:", event.termination_reason);

  if (event.dnc) {
    // caller verbally opted out — number added to org DNC list
    console.log("Contact opted out, added to DNC list.");
  }

  if (event.termination_reason === "user-hangup") {
    // caller hung up — save any collected data
  } else if (event.termination_reason === "bot-transfer") {
    // call was transferred to a human agent
  }
});`;

## on\_session\_end()

Register a handler that fires when a call session ends. Use this to save call data, trigger post-call workflows, or log outcomes.

The `BotSessionEnded` event carries a `termination_reason` field that tells you why the session ended:

| Value | Meaning |
|-------|---------|
| `"user-hangup"` | The caller hung up. |
| `"bot-hangup"` | The agent ended the call (e.g. via `call.hangup()`). |
| `"bot-failure"` | The session ended due to an internal error. |
| `"bot-transfer"` | The call was transferred to another destination. |
| `"voicemail"` | The outbound call reached voicemail. |

The event payload contains a `dnc` boolean field (defaulting to `false`). If the voice agent detects a verbal opt-out during the call, this field is set to `true` and the caller's phone number is automatically added to your organization's Do Not Call list.

<Callout type="info">
DNC detection is exclusive to outbound campaigns (inbound calls are not supported). Opted-out numbers are added directly to your organization-wide DNC list rather than a campaign-specific list.
</Callout>

### Signature

<CodeTabs
  python={{ code: ON_SESSION_END_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_SESSION_END_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The call object. Note: the call is already ended — do not issue commands on it.",
  },
  {
    name: "event",
    type: "BotSessionEnded",
    desc: "Contains `termination_reason` — one of `\"user-hangup\"`, `\"bot-hangup\"`, `\"bot-failure\"`, `\"bot-transfer\"`, `\"voicemail\"`. Also contains `dnc` (`bool` / `boolean`) — `false` by default, `true` when the caller verbally opted out (outbound campaigns only).",
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_SESSION_END_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_SESSION_END_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-session-end" />


---

<!-- section: on-agent-speech -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const ON_AGENT_SPEECH_SIG_PY = `@agent.on_agent_speech
def on_agent_speech(call: guava.Call, event: AgentSpeechEvent) -> None:
    ...`;

export const ON_AGENT_SPEECH_SIG_TS = `agent.onAgentSpeech((call: guava.Call, event: AgentSpeechEvent) => void);`;

export const ON_AGENT_SPEECH_EX_PY = `import logging
from guava.events import AgentSpeechEvent

logger = logging.getLogger(__name__)


@agent.on_agent_speech
def on_agent_speech(call: guava.Call, event: AgentSpeechEvent):
    logger.info("agent speech event: %s", event)

# Output:
# [INFO  15:02:29] agent speech event: sequence=None event_type='agent-speech'
#   utterance='Hi, thank you for calling Thai Palace. My name is Grace.
#   I can help you with the waitlist. ' interrupted=False`;

export const ON_AGENT_SPEECH_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { AgentSpeechEvent } from "@guava-ai/guava-sdk/events";

agent.onAgentSpeech((_call: guava.Call, event: AgentSpeechEvent) => {
  console.log("agent speech event:", JSON.stringify(event));
});`;

## on\_agent\_speech()

<Callout>
  <span className="text-primary font-semibold">Rarely needed.</span> This callback fires for every utterance spoken by the agent. Most implementations will not need it and should instead rely on higher-level callbacks like <a href="/docs/on-question"><code>on_question</code></a> or <a href="/docs/on-task-complete"><code>on_task_complete</code></a>. It is most useful for implementing call surveillance or real-time transcription logging.
</Callout>

Register a handler to receive a callback whenever the agent speaks. The event contains what the agent said and whether it was interrupted by the caller.

The `AgentSpeechEvent` is a pydantic model imported from `guava.events`:

```python
from guava.events import AgentSpeechEvent

class AgentSpeechEvent(BaseEvent):
    event_type: Literal["agent-speech"] = "agent-speech"
    utterance: str
    interrupted: bool = False
```

### Signature

<CodeTabs
  python={{ code: ON_AGENT_SPEECH_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_AGENT_SPEECH_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The active call object.",
  },
  {
    name: "event",
    type: "AgentSpeechEvent",
    desc: "Contains `utterance` (string) and `interrupted` (boolean) fields.",
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_AGENT_SPEECH_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_AGENT_SPEECH_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-agent-speech" />


---

<!-- section: on-caller-speech -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const ON_CALLER_SPEECH_SIG_PY = `@agent.on_caller_speech
def on_caller_speech(call: guava.Call, event: CallerSpeechEvent) -> None:
    ...`;

export const ON_CALLER_SPEECH_SIG_TS = `agent.onCallerSpeech((call: guava.Call, event: CallerSpeechEvent) => void);`;

export const ON_CALLER_SPEECH_EX_PY = `import logging
from guava.events import CallerSpeechEvent

logger = logging.getLogger(__name__)


@agent.on_caller_speech
def on_caller_speech(call: guava.Call, event: CallerSpeechEvent):
    logger.info("caller speech event: %s", event)

# Output:
# [INFO  13:30:43] caller speech event: sequence=None event_type='caller-speech'
#   utterance='Hi Grace.' utterance_id='19d92d6c68b'
# [INFO  13:30:45] caller speech event: sequence=None event_type='caller-speech'
#   utterance='Hi Grace. I am looking' utterance_id='19d92d6c68b'
# [INFO  13:30:46] caller speech event: sequence=None event_type='caller-speech'
#   utterance='Hi Grace. I am looking to make a reservation' utterance_id='19d92d6c68b'
# [INFO  13:30:49] caller speech event: sequence=None event_type='caller-speech'
#   utterance="It's for me" utterance_id='19d92d6deec'
# [INFO  13:30:50] caller speech event: sequence=None event_type='caller-speech'
#   utterance="It is for me and a couple friends." utterance_id='19d92d6deec'`;

export const ON_CALLER_SPEECH_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { CallerSpeechEvent } from "@guava-ai/guava-sdk/events";

agent.onCallerSpeech((_call: guava.Call, event: CallerSpeechEvent) => {
  console.log("caller speech event:", JSON.stringify(event));
});`;

## on\_caller\_speech()

<Callout>
  <span className="text-primary font-semibold">Rarely needed.</span> This callback fires for every utterance spoken by the caller. Most implementations will not need it and should instead rely on higher-level callbacks like <a href="/docs/on-question"><code>on_question</code></a> or <a href="/docs/on-task-complete"><code>on_task_complete</code></a>. It is most useful for implementing call surveillance or real-time transcription logging.
</Callout>

Register a handler to receive a callback whenever caller speech is detected. The event contains what the caller said and an `utterance_id` that distinguishes new utterances from updates to existing ones.

As transcription progresses, you may receive multiple events with the same `utterance_id`. Usually these updates append new words, but there can be slight corrections to previously transcribed words. For example:

- `"Hi."` — `utterance_id='0'`
- `"I am going to the store"` — `utterance_id='1'`
- `"I'm going to the store and"` — `utterance_id='1'` (update to the same utterance)

The `CallerSpeechEvent` is a pydantic model imported from `guava.events`:

```python
from guava.events import CallerSpeechEvent

class CallerSpeechEvent(BaseEvent):
    event_type: Literal["caller-speech"] = "caller-speech"
    utterance: str
    utterance_id: Optional[str] = None
```

### Signature

<CodeTabs
  python={{ code: ON_CALLER_SPEECH_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_CALLER_SPEECH_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The active call object.",
  },
  {
    name: "event",
    type: "CallerSpeechEvent",
    desc: "Contains `utterance` (string) and `utterance_id` (optional string) fields.",
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_CALLER_SPEECH_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_CALLER_SPEECH_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-caller-speech" />


---

<!-- section: on-escalate -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';

export const ON_ESCALATE_SIG_PY = `@agent.on_escalate
def on_escalate(call: guava.Call, event: EscalateEvent) -> None:
    ...`;

export const ON_ESCALATE_SIG_TS = `agent.onEscalate((call: guava.Call, event: EscalateEvent) => Promise<void>);`;

export const ON_ESCALATE_EX_PY = `from guava.events import EscalateEvent

@agent.on_escalate
def on_escalate(call: guava.Call, event: EscalateEvent):
    call.transfer(destination="+15556667777")`;

export const ON_ESCALATE_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { EscalateEvent } from "@guava-ai/guava-sdk/events";

agent.onEscalate(async (call: guava.Call, event: EscalateEvent) => {
  await call.transfer("+15556667777");
});`;

## on\_escalate()

Register a handler that fires when the call needs to be escalated to a human agent.

This callback can be triggered in two ways:

- **By the caller** — the person on the call explicitly asks to speak to a human (e.g. "Can you connect me to a human agent, please?").
- **By the bot** — the agent determines it is unable to service the call properly.

The `EscalateEvent` is a pydantic model imported from `guava.events`:

```python
from guava.events import EscalateEvent

class EscalateEvent(BaseEvent):
    event_type: Literal["escalate"] = "escalate"
    requested_by: Literal["human", "agent"] = "human"
```

<Callout>
  <span className="text-primary font-semibold">Interaction with on_action_request:</span> If you implement the <a href="/docs/on-action-request-execute"><code>on_action_request</code></a> callback, <code>on_escalate</code> will not detect escalation requests made by the human caller — you become responsible for handling those via <code>on_action_request</code>. <code>on_escalate</code> will still fire for escalations initiated by the bot.
</Callout>

### Signature

<CodeTabs
  python={{ code: ON_ESCALATE_SIG_PY, filename: "signature" }}
  typescript={{ code: ON_ESCALATE_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "call",
    type: "Call",
    desc: "The active call object.",
  },
  {
    name: "event",
    type: "EscalateEvent",
    desc: "Contains `requested_by` (string): `'human'` if the caller requested escalation, `'agent'` if the bot initiated it.",
  },
]} />

**Return value:** `None`

### Example

<CodeTabs
  python={{ code: ON_ESCALATE_EX_PY, filename: "controller.py" }}
  typescript={{ code: ON_ESCALATE_EX_TS, filename: "controller.ts" }}
/>

<AutoNextLink currentSection="on-escalate" />


---

<!-- section: set-task -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

## set_task()

`call.set_task()` directs the agent toward a new goal mid-call. It accepts an objective, an ordered checklist of steps, and a task ID for binding completion handlers.

export const SET_TASK_SIG_PY = `call.set_task(
    task_id: str,
    objective: str = "",
    checklist: list[Field | Say | str] | None = None,
    completion_criteria: str = "",
)`;

export const SET_TASK_SIG_TS = `await call.setTask({
  taskId: string,
  objective?: string,
  checklist?: (FieldItem | SayItem | string)[],
  completionCriteria?: string,
})`;

<CodeTabs
  python={{ code: SET_TASK_SIG_PY, filename: "signature" }}
  typescript={{ code: SET_TASK_SIG_TS, filename: "signature" }}
/>

<Callout>
  <span className="text-primary font-semibold">Full reference:</span> See the <a href="/docs/tasks" className="text-primary hover:underline">Task</a> page for parameter details, checklist item types, and a complete example.
</Callout>

<AutoNextLink currentSection="set-task" />


---

<!-- section: set-persona -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const SET_PERSONA_SIG_PY = `call.set_persona(
    organization_name: str | None = None,
    agent_name: str | None = None,
    agent_purpose: str | None = None,
    voice: str | None = None,
    speech_speed: Literal["x-slow", "slow", "medium", "fast", "x-fast"] | None = None,
)`;

export const SET_PERSONA_SIG_TS = `await call.setPersona({
  organizationName?: string,
  agentName?: string,
  agentPurpose?: string,
  voice?: string,
  speechSpeed?: "x-slow" | "slow" | "medium" | "fast" | "x-fast",
})`;

export const SET_PERSONA_EX_PY = `call.set_persona(
    organization_name="Bright Smile Dental",
    agent_name="Alex",
    agent_purpose="You are calling patients to help them schedule and confirm dental appointments",
    voice="grace",
)`;

export const SET_PERSONA_EX_TS = `await call.setPersona({
  organizationName: "Bright Smile Dental",
  agentName: "Alex",
  agentPurpose: "Help patients schedule dental appointments",
})`;

## set\_persona()

`call.set_persona()` is deliberately minimal. Give it the organization name and let the agent figure out the tone. You don't need to specify a voice style, a greeting template, or a list of prohibited phrases — Guava's defaults are professional and natural.

<CodeTabs
  python={{ code: SET_PERSONA_SIG_PY, filename: "signature" }}
  typescript={{ code: SET_PERSONA_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "organization_name",
    type: "str | None",
    desc: "The organization the agent represents. Used in introductions.",
  },
  {
    name: "agent_name",
    type: "str | None",
    desc: "The agent's first name. Defaults to a generic 'assistant' style.",
  },
  {
    name: "agent_purpose",
    type: "str | None",
    desc: "A sentence describing why the agent is calling. Sets the LLM's operating context.",
  },
  {
    name: "voice",
    type: "str | None",
    default: '"grace"',
    desc: 'The TTS voice to use. Options: "grace" (Southeastern U.S. female), "andie" (U.S. female), "otto" (U.S. male), "colin" (U.S. male), "kyle" (U.S. male), "kate" (British female), or "jack" (British male). For languages outside of English, only the "grace" voice is supported.',
  },
  {
    name: "speech_speed",
    type: "str | None",
    default: '"medium"',
    desc: 'How quickly the agent speaks. Options: "x-slow", "slow", "medium", "fast", or "x-fast". Changing it mid-call takes effect on the agent\'s next utterance.',
  },
]} />

### Example

<CodeTabs
  python={{ code: SET_PERSONA_EX_PY, filename: "example.py" }}
  typescript={{ code: SET_PERSONA_EX_TS, filename: "example.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Tip:</span> Include the contact's name in `agent_purpose` to help the agent personalize the conversation naturally.
</Callout>

<AutoNextLink currentSection="set-persona" />


---

<!-- section: send-instruction -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const SEND_INSTRUCTION_SIG_PY = `call.send_instruction(instruction: str) -> None`;

export const SEND_INSTRUCTION_SIG_TS = `await call.sendInstruction(instruction: string): Promise<void>`;

export const SEND_INSTRUCTION_EX_PY = `@agent.on_task_complete("collect_order_id")
def on_order_id_collected(call: guava.Call):
    order = lookup_order(call.get_field("order_id"))
    call.send_instruction(
        f"Order #{order['id']} is {order['status']} "
        f"with an estimated delivery of {order['eta']}. "
        f"Share this with the caller naturally."
    )`;

export const SEND_INSTRUCTION_EX_TS = `agent.onTaskComplete("collect_order_id", async (call: guava.Call) => {
  const order = await lookupOrder(await call.getField("order_id") as string);
  await call.sendInstruction(
    \`Order #\${order.id} is \${order.status} \`
    + \`with an estimated delivery of \${order.eta}. \`
    + \`Share this with the caller naturally.\`
  );
})`;

## send\_instruction()

`call.send_instruction(instruction)` sends a real-time instruction to the agent without changing the current task. Use it for context injection and behavioral nudges.

### Signature

<CodeTabs
  python={{ code: SEND_INSTRUCTION_SIG_PY, filename: "signature" }}
  typescript={{ code: SEND_INSTRUCTION_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "instruction",
    type: "str",
    desc: "A real-time instruction to pass to the agent. Does not change the current task.",
  },
]} />

**Return value:** `None` / `Promise<void>`

### Example

<CodeTabs
  python={{ code: SEND_INSTRUCTION_EX_PY, filename: "example.py" }}
  typescript={{ code: SEND_INSTRUCTION_EX_TS, filename: "example.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Tip:</span> Unlike `call.set_task()`, `call.send_instruction()` doesn't replace the agent's current objective. Use it to inject context or steer behavior mid-conversation — for example, after a database lookup reveals something the agent should know.
</Callout>

<AutoNextLink currentSection="send-instruction" />


---

<!-- section: get-set-variable -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const SIG_PY = `call.set_variable(key: str, value: Any) -> None
call.get_variable(key: str) -> Any`;

export const SIG_TS = `await call.setVariable(key: string, value: any): Promise<void>
await call.getVariable(key: string): Promise<any>`;

export const SET_GET_VARIABLE_EX_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    # Variables seeded via call_phone(variables={...}) are readable immediately
    patient_name = call.get_variable("patient_name")
    call.reach_person(contact_full_name=patient_name)


@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str):
    if outcome == "available":
        call.set_task(
            "confirmed",
            objective="Confirm the appointment and answer any questions.",
        )


@agent.on_task_complete("confirmed")
def on_confirmed(call: guava.Call):
    call.hangup()`;

export const SET_GET_VARIABLE_EX_TS = `agent.onCallStart(async (call: guava.Call) => {
  // Variables seeded via callPhone({ variables: {...} }) are readable immediately
  const patientName = await call.getVariable("patientName");
  await call.reachPerson(patientName);
});

agent.onReachPerson(async (call: guava.Call, outcome: string) => {
  if (outcome === "available") {
    await call.setTask({
      objective: "Confirm the appointment and answer any questions.",
    });
  }
});

agent.onTaskComplete("confirmed", async (call: guava.Call) => {
  await call.hangup();
});`;

## set\_variable() / get\_variable()

Call variables are provided as a convenient way to pass per-call data (patient name, account ID, etc.) between agent handlers.
Variables can be seeded when the call starts and read or updated at any point during the call.

<CodeTabs
  python={{ code: SIG_PY, filename: "signature" }}
  typescript={{ code: SIG_TS, filename: "signature" }}
/>

### Valid variable values

Variable values must be JSON-serializable: strings, numbers, booleans, `None`, and dicts/lists composed of those types.

### Seeding variables at call start

For the following types of calls, variables can be seeded at the start.

- **Outbound calls** — pass a `variables` dict to `call_phone()` / `callPhone()`
- **Campaigns** — each contact's `data` dict becomes that contact's variables

export const CALL_STATE_PY = `r = redis.Redis()
call_state: dict[str, dict] = {}

@agent.on_call_start
def on_call_start(call: guava.Call):
    # In-memory — lost on process restart
    call_state[call.id] = {"stage": "intro"}

    # Redis — survives restarts
    r.set(f"call_state:{call.id}", json.dumps({"stage": "intro"}), ex=3600)`;

export const CALL_STATE_TS = `const r = redis.createClient();
const callState: Record<string, Record<string, unknown>> = {};

agent.onCallStart(async (call: guava.Call) => {
  // In-memory — lost on process restart
  callState[call.id] = { stage: "intro" };

  // Redis — survives restarts
  await r.set(\`call_state:\${call.id}\`, JSON.stringify({ stage: "intro" }), { EX: 3600 });
});`;

### Other ways to store call state

As an alternative to call variables, you can keep per-call state in an in-process dictionary keyed by `call.id`.

That said, we only recommend this for simple use cases. If your process restarts, any in-memory state will be lost.
For durable per-call state, use Redis or another session store keyed by `call.id`.

<CodeTabs
  python={{ code: CALL_STATE_PY }}
  typescript={{ code: CALL_STATE_TS }}
/>


### Example

<CodeTabs
  python={{ code: SET_GET_VARIABLE_EX_PY, filename: "example.py" }}
  typescript={{ code: SET_GET_VARIABLE_EX_TS, filename: "example.ts" }}
/>


<AutoNextLink currentSection="get-set-variable" />


---

<!-- section: set-language-mode -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const SET_LANGUAGE_MODE_SIG_PY = `call.set_language_mode(
    primary: Language = "english",
    secondary: list[Language] | None = None,
)`;

export const SET_LANGUAGE_MODE_SIG_TS = `await call.setLanguageMode({
  primary?: Language,   // default: "english"
  secondary?: Language[],
})

// Language = "english" | "spanish" | "french" | "german" | "italian"`;

export const SET_LANGUAGE_MODE_EX1_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_persona(organization_name="Harper Valley Property Insurance")
    call.set_language_mode(primary="english", secondary=["spanish"])
    call.set_task(
        task_id="intro",
        objective="Answer questions regarding property insurance policy.",
    )`;

export const SET_LANGUAGE_MODE_EX1_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.setPersona({ organizationName: "Harper Valley Property Insurance" });
  await call.setLanguageMode({ primary: "english", secondary: ["spanish"] });
  await call.setTask({
    taskId: "intro",
    objective: "Answer questions regarding property insurance policy.",
  });
});`;

export const SET_LANGUAGE_MODE_EX2_PY = `call.set_language_mode(
    primary="english",
    secondary=["spanish", "french", "german"],
)`;

export const SET_LANGUAGE_MODE_EX2_TS = `await call.setLanguageMode({
  primary: "english",
  secondary: ["spanish", "french", "german"],
});`;

## set\_language\_mode()

Configures the voice agent to understand and respond in additional languages beyond English. The agent starts in the primary language and switches to a secondary language when the caller requests it or speaks in that language.

<CodeTabs
  python={{ code: SET_LANGUAGE_MODE_SIG_PY, filename: "signature" }}
  typescript={{ code: SET_LANGUAGE_MODE_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "primary",
    type: "Language",
    default: '"english"',
    desc: "The language the agent starts the conversation in.",
  },
  {
    name: "secondary",
    type: "list[Language] | None",
    default: "None",
    desc: "Additional languages the agent can switch to when the caller requests them.",
  },
]} />

The `Language` type is defined as:

```
Literal["english", "spanish", "french", "german", "italian"]
```

**Return value:** `None` / `Promise<void>`

### Example: single secondary language

<CodeTabs
  python={{ code: SET_LANGUAGE_MODE_EX1_PY, filename: "example.py" }}
  typescript={{ code: SET_LANGUAGE_MODE_EX1_TS, filename: "example.ts" }}
/>

### Example: multiple secondary languages

<CodeTabs
  python={{ code: SET_LANGUAGE_MODE_EX2_PY, filename: "example.py" }}
  typescript={{ code: SET_LANGUAGE_MODE_EX2_TS, filename: "example.ts" }}
/>

### Transcript behavior

- There is no auto-translation on the transcript. Each turn appears in the language it was spoken in — if the caller speaks Spanish, that turn is in Spanish; if they speak English, that turn is in English.
- There is currently no per-turn language marker in the transcript.

### Edge cases

- If `secondary` is `None` or empty, the agent operates in `primary` only (the current default behavior).
- When a non-English language is detected during a call, the system automatically switches to a language-specific TTS voice.
- The `grace` voice has clones for Spanish, French, German, and Italian. If no dedicated clone exists for a voice + language combination, the base voice is used.


<Callout>
  <span className="text-primary font-semibold">Compliance:</span> English and Spanish are currently supported for HITRUST / PCI-compliant deployments. All languages other than English and Spanish are not. Support for other languages is planned.
</Callout>

<AutoNextLink currentSection="set-language-mode" />


---

<!-- section: transfer -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const TRANSFER_SIG_PY = `call.transfer(
    destination: str,
    instructions: str | None = None,
)`;

export const TRANSFER_SIG_TS = `await call.transfer(
  destination: string,
  instructions?: string,
): Promise<void>`;

export const TRANSFER_EX_PY = `@agent.on_task_complete("collect_issue")
def on_issue_collected(call: guava.Call):
    call.transfer(
        destination="+18005550199",
        instructions="Let the caller know you're transferring them to a service representative.",
    )`;

export const TRANSFER_EX_TS = `agent.onTaskComplete("collect_issue", async (call: guava.Call) => {
  await call.transfer(
    "+18005550199",
    "Let the caller know you're transferring them to a service representative.",
  );
});`;

## transfer()

`call.transfer()` hands the active call off to another phone number or SIP address. It is a soft transfer — the agent notifies the caller before bridging, so there's no abrupt silence or dead air.

<CodeTabs
  python={{ code: TRANSFER_SIG_PY, filename: "signature" }}
  typescript={{ code: TRANSFER_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "destination",
    type: "str",
    desc: "The phone number or SIP address to transfer the call to.",
  },
  {
    name: "instructions",
    type: "str | None",
    desc: 'What the agent should say before bridging. Defaults to a generic "I\'ll transfer you now" message.',
  },
]} />

### Example

<CodeTabs
  python={{ code: TRANSFER_EX_PY, filename: "example.py" }}
  typescript={{ code: TRANSFER_EX_TS, filename: "example.ts" }}
/>

<AutoNextLink currentSection="transfer" />


---

<!-- section: hangup -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const HANGUP_SIG_PY = `call.hangup(final_instructions: str = "")`;

export const HANGUP_SIG_TS = `await call.hangup(final_instructions?: string): Promise<void>`;

export const HANGUP_EX_PY = `@agent.on_task_complete("collect_order")
def on_order_collected(call: guava.Call):
    call.hangup(
        final_instructions="Thank them for their time, mention the confirmation number, then hang up."
    )`;

export const HANGUP_EX_TS = `agent.onTaskComplete("collect_order", async (call: guava.Call) => {
  await call.hangup(
    "Thank them for their time, mention the confirmation number, then hang up."
  );
});`;

## hangup()

`call.hangup()` is a soft hangup. Rather than cutting the call immediately, it hands the agent a final instruction and lets it close the conversation naturally before ending the call. Callers hear a proper goodbye.

<CodeTabs
  python={{ code: HANGUP_SIG_PY, filename: "signature" }}
  typescript={{ code: HANGUP_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "final_instructions",
    type: "str",
    desc: "What the agent should do before hanging up. If omitted, the agent ends the conversation naturally with no special instructions.",
  },
]} />

### Example

<CodeTabs
  python={{ code: HANGUP_EX_PY, filename: "example.py" }}
  typescript={{ code: HANGUP_EX_TS, filename: "example.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Tip:</span> Be specific in your final instructions. The agent will try to fulfill them naturally — including mentioning a confirmation number, scheduling next steps, or expressing appropriate warmth.
</Callout>

<AutoNextLink currentSection="hangup" />


---

<!-- section: reach-person -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, PropTable } from '../views/docs/prose';
export const REACH_PERSON_SIG_PY = `def reach_person(
    contact_full_name: str,
    *,
    greeting: str | None = None,
    voicemail_message: str | None = None,
    voicemail_hangup: bool = False,
    outcomes: list[ReachPersonOutcome] | None = None,
)`;

export const REACH_PERSON_SIG_TS = `reachPerson(
  contactFullName: string,
  options?: {
    greeting?: string;
    voicemailMessage?: string;
    voicemailHangup?: boolean;
    outcomes?: ReachPersonOutcome[];
  },
): Promise<void>`;

export const REACH_PERSON_EX_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.reach_person(
        contact_full_name=call.get_variable("contact_name"),
        voicemail_message="Please give us a call back at your convenience."
    )

@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str):
    if outcome == "available":
        call.set_task(
            "main_task",
            checklist=[...],
        )
    else:
        call.hangup("Appropriately end the call.")`;

export const REACH_PERSON_EX_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.reachPerson(await call.getVariable("contactName") as string, {
    voicemailMessage: "Please give us a call back at your convenience.",
  });
});

agent.onReachPerson(async (call: guava.Call, outcome: string) => {
  if (outcome === "available") {
    await call.setTask({ taskId: "main_task", checklist: [...] });
  } else {
    await call.hangup("Appropriately end the call.");
  }
})`;

## reach\_person()

For outbound calls, `reach_person()` handles the critical first step: confirming you have the right person on the line before proceeding. It automatically handles answering machines, gatekeepers, wrong numbers, and refusals.

<CodeTabs
  python={{ code: REACH_PERSON_SIG_PY, filename: "signature" }}
  typescript={{ code: REACH_PERSON_SIG_TS, filename: "signature" }}
/>

<PropTable rows={[
  {
    name: "contact_full_name",
    type: "str",
    desc: "The full name of the person you're trying to reach.",
  },
  {
    name: "greeting",
    type: "str | None",
    default: "None",
    desc: "Custom greeting message. Overrides the default introduction.",
  },
  {
    name: "voicemail_message",
    type: "str | None",
    default: "None",
    desc: "Message to leave if voicemail is reached. Mutually exclusive with voicemail_hangup and with set_voicemail_action().",
  },
  {
    name: "voicemail_hangup",
    type: "bool",
    default: "False",
    desc: "Immediately hang up if voicemail is reached. Mutually exclusive with voicemail_message and with set_voicemail_action().",
  },
  {
    name: "outcomes",
    type: "list[ReachPersonOutcome] | None",
    default: "None",
    desc: "Custom outcome routing. Defaults to five outcomes: available, unavailable, voicemail, wrong_number, and do_not_contact. Use this to define additional or different outcomes.",
  },
]} />

<CodeTabs
  python={{ code: REACH_PERSON_EX_PY, filename: "example.py" }}
  typescript={{ code: REACH_PERSON_EX_TS, filename: "example.ts" }}
/>



### What happens on the call

When `reach_person()` is invoked, the agent automatically:

1. **Greets** whoever answers and introduces itself (organization + purpose).
2. **Asks for the contact** by name. If someone else answered, asks to speak with or be transferred to the contact.
3. **Determines availability** and records the contact's availability in a `contact_availability` field.
4. **Fires `agent.on_reach_person`** with the outcome key. The five default outcomes are:
   - `"available"` — the intended contact is on the line.
   - `"unavailable"` — someone else or an IVR answered and the contact could not be reached.
   - `"voicemail"` — an answering machine or voicemail system was reached.
   - `"wrong_number"` — the number does not belong to the contact.
   - `"do_not_contact"` — the contact asked not to be called again.

   If you provided custom `outcomes`, those are used instead.

### Voicemail handling

<Callout>
  <span className="text-primary font-semibold">Warning:</span> <code>reach_person()</code> and <code>set_voicemail_action()</code> both handle voicemail and <strong>cannot be used together</strong>. If you set <code>voicemail_message</code> or <code>voicemail_hangup</code> on <code>reach_person()</code>, do not call <code>set_voicemail_action()</code> — and vice versa. Using both raises an error.
</Callout>

### Common mistake: redundant introductions

<Callout>
  <span className="text-primary font-semibold">Warning:</span> By the time `on_reach_person` fires, the agent has already introduced itself and stated the purpose of the call. Do **not** re-introduce in the first task after `reach_person`.
</Callout>

```python
# WRONG — redundant introduction
@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str):
    if outcome == "available":
        call.set_task("survey", checklist=[
            guava.Say("Hi, this is Grace from Acme Corp, I'm calling about..."),  # Already said this
            ...
        ])

# RIGHT — go straight to content
@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str):
    if outcome == "available":
        call.set_task("survey", checklist=[
            guava.Say("I just have a few quick questions for you today."),
            ...
        ])
```

<AutoNextLink currentSection="reach-person" />


---

<!-- section: set-voicemail-action -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const SET_VOICEMAIL_ACTION_SIG_PY = `call.set_voicemail_action(
    hangup: bool = False,
    message: str | None = None,
)`;

export const SET_VOICEMAIL_ACTION_SIG_TS = `await call.setVoicemailAction(
  action: { hangup: true } | { message: string },
): Promise<void>`;

export const SET_VOICEMAIL_ACTION_EX_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_voicemail_action(
        message="Hi, this is Alex from Bright Smile Dental. Please call us back at 555-0100 to confirm your appointment.",
    )`;

export const SET_VOICEMAIL_ACTION_EX_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.setVoicemailAction({
    message: "Hi, this is Alex from Bright Smile Dental. Please call us back at 555-0100 to confirm your appointment.",
  });
});`;

## set\_voicemail\_action()

`set_voicemail_action()` tells the agent what to do if it reaches an answering machine.

<Callout>
  <span className="text-primary font-semibold">Warning:</span> <code>set_voicemail_action()</code> and <code>reach_person()</code> both handle voicemail and <strong>cannot be used together</strong>. If you are using <code>reach_person()</code>, set voicemail behavior there via its <code>voicemail_message</code> or <code>voicemail_hangup</code> parameters instead. Using both raises an error.
</Callout>

<CodeTabs
  python={{ code: SET_VOICEMAIL_ACTION_SIG_PY, filename: "signature" }}
  typescript={{ code: SET_VOICEMAIL_ACTION_SIG_TS, filename: "signature" }}
/>

### Example

<CodeTabs
  python={{ code: SET_VOICEMAIL_ACTION_EX_PY, filename: "example.py" }}
  typescript={{ code: SET_VOICEMAIL_ACTION_EX_TS, filename: "example.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Tip:</span> You must specify exactly one of <code>hangup</code> or <code>message</code> — passing both or neither raises an error.
</Callout>

<AutoNextLink currentSection="set-voicemail-action" />


---

<!-- section: read-script -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';
export const READ_SCRIPT_SIG_PY = `def read_script(script: str)`;

export const READ_SCRIPT_SIG_TS = `readScript(script: string): Promise<void>`;

export const READ_SCRIPT_EX_PY = `@agent.on_call_start
def on_call_start(call: guava.Call):
    call.read_script(
        "Hello! This is a courtesy call from Bright Smile Dental. "
        "We're confirming your appointment tomorrow at 2 PM."
    )
    call.set_task(
        "confirm_appointment",
        checklist=[
            guava.Field(key="confirmed", field_type="text",
                        description="Did they confirm the appointment?"),
        ],
    )

@agent.on_task_complete("confirm_appointment")
def on_confirmed(call: guava.Call):
    call.hangup()`;

export const READ_SCRIPT_EX_TS = `agent.onCallStart(async (call: guava.Call) => {
  await call.readScript(
    "Hello! This is a courtesy call from Bright Smile Dental. "
    + "We're confirming your appointment tomorrow at 2 PM."
  );
  await call.setTask({
    taskId: "confirm_appointment",
    checklist: [
      guava.Field({
        key: "confirmed",
        fieldType: "text",
        description: "Did they confirm the appointment?",
      }),
    ],
  });
});

agent.onTaskComplete("confirm_appointment", async (call) => {
  await call.hangup();
})`;

## read\_script()

`read_script()` speaks a verbatim opening statement at the very start of a call, before any LLM involvement. Use it for compliance disclosures, scripted greetings, or anything that must be delivered word-for-word.

<CodeTabs
  python={{ code: READ_SCRIPT_SIG_PY, filename: "signature" }}
  typescript={{ code: READ_SCRIPT_SIG_TS, filename: "signature" }}
/>

<CodeTabs
  python={{ code: READ_SCRIPT_EX_PY, filename: "example.py" }}
  typescript={{ code: READ_SCRIPT_EX_TS, filename: "example.ts" }}
/>

<Callout>
  <span className="text-primary font-semibold">Note:</span> Unlike `Say` in a checklist, `read_script()` fires before any LLM turn and before any task is set. It's the agent's very first words.
</Callout>

<AutoNextLink currentSection="read-script" />


---

<!-- section: add-info -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { AutoNextLink, PropTable } from '../views/docs/prose';

export const ADD_INFO_SIG_PY = `def add_info(label: str, info: Any) -> None`;

export const ADD_INFO_SIG_TS = `addInfo(label: string, info: any): Promise<void>`;

export const ADD_INFO_EX_PY = `AMENITIES_INFO = {
    "amenities": [
        "Rooftop pool",
        "Full-service spa",
        "Fitness center",
        "Business center",
        "Complimentary airport shuttle",
    ]
}

agent = guava.Agent(
    name="Riley",
    organization="Oceanfront Hotel",
    purpose="You are the head concierge tasked with assisting guests with questions and reservations.",
)

@agent.on_call_start
def on_call_start(call: guava.Call):
    call.add_info("amenities_details", AMENITIES_INFO)`;

export const ADD_INFO_EX_TS = `const AMENITIES_INFO = {
  amenities: [
    "Rooftop pool",
    "Full-service spa",
    "Fitness center",
    "Business center",
    "Complimentary airport shuttle",
  ],
};

const agent = new guava.Agent({
  name: "Riley",
  organization: "Oceanfront Hotel",
  purpose: "You are the head concierge tasked with assisting guests with questions and reservations.",
});

agent.onCallStart(async (call: guava.Call) => {
  await call.addInfo("amenities_details", AMENITIES_INFO);
})`;

## add\_info()

`add_info()` can be used to provide Guava agents with additional context. Once called, the information persists for the duration of the call and
surfaces naturally when relevant. It can be called at the start of a call as well as any time during a call.

<CodeTabs
  python={{ code: ADD_INFO_SIG_PY, filename: "signature" }}
  typescript={{ code: ADD_INFO_SIG_TS, filename: "signature" }}
/>

### Example

<CodeTabs
  python={{ code: ADD_INFO_EX_PY, filename: "example.py" }}
  typescript={{ code: ADD_INFO_EX_TS, filename: "example.ts" }}
/>

<AutoNextLink currentSection="add-info" />


---

<!-- section: get-field -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';
export const GET_FIELD_SIG_PY = `def get_field(field_key: str) -> str | int | dict | None`;

export const GET_FIELD_SIG_TS = `getField(key: string): Promise<any | null>`;

export const GET_FIELD_EX_PY = `@agent.on_task_complete("schedule_appointment")
def on_appointment_scheduled(call: guava.Call):
    appointment_time = call.get_field("appointment_time")
    patient_name = call.get_field("patient_name")
    # Write to your CRM / EHR
    save_appointment(patient_name, appointment_time)
    call.hangup()`;

export const GET_FIELD_EX_TS = `agent.onTaskComplete("schedule_appointment", async (call: guava.Call) => {
  const appointmentTime = await call.getField("appointment_time");
  const patientName = await call.getField("patient_name");
  // Write to your CRM / EHR
  saveAppointment(patientName, appointmentTime);
  await call.hangup();
})`;

## get_field()

After the checklist completes and `agent.on_task_complete` fires, use `call.get_field()` to retrieve collected values by their key. This is where you write results to your CRM, database, or EHR.

<CodeTabs
  python={{ code: GET_FIELD_SIG_PY, filename: "signature" }}
  typescript={{ code: GET_FIELD_SIG_TS, filename: "signature" }}
/>

<CodeTabs
  python={{ code: GET_FIELD_EX_PY, filename: "example.py" }}
  typescript={{ code: GET_FIELD_EX_TS, filename: "example.ts" }}
/>

### Return types by field type

The type of the value returned by `get_field()` depends on the field's `field_type`:

| `field_type` | Returned value |
|---|---|
| `text` | `str` |
| `date` | `dict` with keys `year`, `month`, `day` (all `int`) |
| `integer` | `int` |
| `multiple_choice` | `str` (guaranteed to be one of the values in `choices` or returned by `choice_generator`) |
| `calendar_slot` | ISO-8601 datetime string (e.g. `"2022-12-25T16:30"`) |

<Callout>
  <span className="text-primary font-semibold">Tip:</span> You can call `get_field()` at any point after the field has been collected — not just in `on_task_complete`. Use it in mid-call callbacks to personalize subsequent steps.
</Callout>

<AutoNextLink currentSection="get-field" />


---

<!-- section: intent-helpers -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';

export const NEW_INTENT_RECOGNIZER_SIG_PY = `from guava.helpers.llm import IntentRecognizer

IntentRecognizer(intent_choices: list[str] | dict[str, str])
recognizer.classify(intent: str) -> list[SuggestedAction] | None`;

export const NEW_INTENT_RECOGNIZER_SIG_TS = `import { IntentRecognizer } from "@guava-ai/guava-sdk/helpers";

new IntentRecognizer(intentChoices: string[] | Record<string, string>)
await recognizer.classify(intent: string): Promise<SuggestedAction[] | null>`;

export const NEW_INTENT_RECOGNIZER_EX_PY = `import guava
from guava import Agent, SuggestedAction
from guava.helpers.llm import IntentRecognizer

agent = Agent(
    name="Support",
    organization="Acme Corp",
    purpose="Help the caller with their support request.",
)

intent_recognizer = IntentRecognizer({
    'check order status': 'Caller wants to look up the status of an existing order.',
    'bill pay': 'Caller wants to make a payment or ask about their bill.',
    'anything else': 'Caller has a request that does not fit the above categories.',
})

@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction | list[SuggestedAction] | None:
    return intent_recognizer.classify(request)

@agent.on_action("check order status")
def check_order_status(call: guava.Call):
    call.transfer("+15555555555", "Transfer the caller to the order status team.")

@agent.on_action("bill pay")
def bill_pay(call: guava.Call):
    call.transfer("+15555555555", "Transfer the caller to billing.")

@agent.on_action("anything else")
def anything_else(call: guava.Call):
    call.transfer("+15555555555", "Connect the caller with a live agent.")`;

export const NEW_INTENT_RECOGNIZER_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { IntentRecognizer } from "@guava-ai/guava-sdk/helpers";

const agent = new guava.Agent({
  name: "Support",
  organization: "Acme Corp",
  purpose: "Help the caller with their support request.",
});

const intentRecognizer = new IntentRecognizer({
  "check order status": "Caller wants to look up the status of an existing order.",
  "bill pay": "Caller wants to make a payment or ask about their bill.",
  "anything else": "Caller has a request that does not fit the above categories.",
});

agent.onActionRequest(async (_call: guava.Call, request: string) => {
  return intentRecognizer.classify(request);
});

agent.onAction("check order status", async (call: guava.Call) => {
  call.transfer("+15555555555", "Transfer the caller to the order status team.");
});

agent.onAction("bill pay", async (call: guava.Call) => {
  call.transfer("+15555555555", "Transfer the caller to billing.");
});

agent.onAction("anything else", async (call: guava.Call) => {
  call.transfer("+15555555555", "Connect the caller with a live agent.");
})`;

export const INTENT_RECOGNIZER_SIG_PY = `from guava.helpers.openai import IntentRecognizer

IntentRecognizer(intent_choices: list[str] | dict[str, str], client: openai.OpenAI | None = None)
recognizer.classify(intent: str) -> str | None`;

export const INTENT_RECOGNIZER_SIG_TS = `import { IntentRecognizer } from "@guava-ai/guava-sdk/helpers/openai";

const recognizer = new IntentRecognizer(choices, logger);`;

export const INTENT_RECOGNIZER_EX_PY = `import guava
from guava import Agent, SuggestedAction
from guava.helpers.openai import IntentRecognizer

agent = Agent(
    name="Support",
    organization="Acme Corp",
    purpose="Help the caller with their support request.",
)

intent_recognizer = IntentRecognizer(
    ['check order status', 'bill pay', 'anything else']
)

@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction:
    return SuggestedAction(key=intent_recognizer.classify(request))

@agent.on_action("check order status")
def check_order_status(call: guava.Call):
    call.transfer("+15555555555", "Transfer the caller to the order status team.")

@agent.on_action("bill pay")
def bill_pay(call: guava.Call):
    call.transfer("+15555555555", "Transfer the caller to billing.")

@agent.on_action("anything else")
def anything_else(call: guava.Call):
    call.transfer("+15555555555", "Connect the caller with a live agent.")`;

export const INTENT_RECOGNIZER_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { IntentRecognizer } from "@guava-ai/guava-sdk/helpers/openai";
import { getDefaultLogger } from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  name: "Support",
  organization: "Acme Corp",
  purpose: "Help the caller with their support request.",
});

const choices = ["check_order_status", "bill_pay", "other"] as const;
const recognizer = new IntentRecognizer(choices, getDefaultLogger());

agent.onActionRequest(async (_call: guava.Call, request: string) => {
  const key = await recognizer.classify(request);
  return { key };
});

agent.onAction("check_order_status", async (call: guava.Call) => {
  call.transfer("+15555555555", "Transfer the caller to the order status team.");
});

agent.onAction("bill_pay", async (call: guava.Call) => {
  call.transfer("+15555555555", "Transfer the caller to billing.");
});

agent.onAction("other", async (call: guava.Call) => {
  call.transfer("+15555555555", "Connect the caller with a live agent.");
})`;

export const INTENT_CLARIFIER_SIG_PY = `from guava.helpers.openai import IntentClarifier

IntentClarifier(intent_choices: list[str] | dict[str, str], client: openai.OpenAI | None = None)
clarifier.propose_choices(intent: str) -> list[str]`;

export const INTENT_CLARIFIER_SIG_TS = `// IntentClarifier is not yet available in TypeScript.
// Use IntentRecognizer for single-match classification.`;

export const INTENT_CLARIFIER_EX_PY = `import guava
from guava import Agent, SuggestedAction
from guava.helpers.openai import IntentClarifier

agent = Agent(
    name="Scheduler",
    organization="Acme Corp",
    purpose="Help callers manage their appointments.",
)

intent_clarifier = IntentClarifier(
    ['reschedule appointment', 'cancel appointment', 'check appointment time']
)

@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction:
    matches = intent_clarifier.propose_choices(request)
    if len(matches) == 1:
        # Unambiguous — proceed directly
        return SuggestedAction(key=matches[0])
    elif len(matches) > 1:
        # Ambiguous — route to the most likely match; agent will confirm with caller
        return SuggestedAction(key=matches[0], description=f"Caller may have meant one of: {matches}")
    # len == 0: no match, return nothing so the agent keeps listening`;

export const INTENT_CLARIFIER_EX_TS = `// IntentClarifier is not yet available in TypeScript.`;

## Intent Helpers

Guava provides an intent classification helper for routing caller requests. `IntentRecognizer` classifies caller utterances into your predefined intents and returns matching actions for the dialog engine to handle.

### IntentRecognizer

`IntentRecognizer` classifies a free-text caller utterance against your predefined intent labels and returns all plausible matches as `SuggestedAction` objects. Use it inside `on_action_request()` to map caller language to routing decisions — return the full list and let the dialog engine handle disambiguation automatically.

**Import:** `from guava.helpers.llm import IntentRecognizer`

<CodeTabs
  python={{ code: NEW_INTENT_RECOGNIZER_SIG_PY, filename: "signature" }}
  typescript={{ code: NEW_INTENT_RECOGNIZER_SIG_TS, filename: "signature" }}
/>

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `intent_choices` | `list[str] \| dict[str, str]` | Yes | The set of intents to classify into. Pass a list of choice strings, or a dict mapping choice strings to plain-English descriptions to help IntentRecognizer disambiguate meaning. When a dict is passed, descriptions are also attached to the returned `SuggestedAction` objects so the dialog engine can use them when disambiguating multiple matches with the caller. |

**`classify(intent: str) -> list[SuggestedAction] | None`** — Returns all choices from `intent_choices` that plausibly match `intent`, ordered by likelihood. Returns `None` if no choice matches. It is recommended to return the full list from `on_action_request` to let the dialog engine handle disambiguation automatically.

<CodeTabs
  python={{ code: NEW_INTENT_RECOGNIZER_EX_PY, filename: "support_agent.py" }}
  typescript={{ code: NEW_INTENT_RECOGNIZER_EX_TS, filename: "support_agent.ts" }}
/>

---

### IntentRecognizer (openai — deprecated)

<Callout>
  <span className="text-primary font-semibold">Deprecated:</span> `IntentRecognizer` from `guava.helpers.openai` is deprecated. Use the new `IntentRecognizer` from `guava.helpers.llm` above instead.
</Callout>

`IntentRecognizer` classifies a free-text caller utterance into one of your predefined intent labels. Use it inside `on_action_request()` to map vague caller language to clean routing decisions.

<CodeTabs
  python={{ code: INTENT_RECOGNIZER_SIG_PY, filename: "signature" }}
  typescript={{ code: INTENT_RECOGNIZER_SIG_TS, filename: "signature" }}
/>

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `intent_choices` | `list[str] \| dict[str, str]` | Yes | The set of intents to classify into. Pass a list of choice strings, or a dict mapping choice strings to plain-English descriptions (descriptions improve accuracy on similar-sounding choices). |
| `client` | `openai.OpenAI` | No | An OpenAI client to use. If omitted, a client is created automatically. |

**`classify(intent: str) -> str | None`** — Returns the single choice string from `intent_choices` that best matches `intent`, or `None` if the model cannot match any choice. When `intent_choices` is a `dict`, the keys are the valid return values; values are used only as descriptions to guide the model.

<CodeTabs
  python={{ code: INTENT_RECOGNIZER_EX_PY, filename: "support_agent.py" }}
  typescript={{ code: INTENT_RECOGNIZER_EX_TS, filename: "support_agent.ts" }}
/>

### IntentClarifier (deprecated)

<Callout>
  <span className="text-primary font-semibold">Deprecated:</span> `IntentClarifier` from `guava.helpers.openai` is deprecated. Use the new `IntentRecognizer` from `guava.helpers.llm` above instead — it returns all plausible matches by default, replacing the need for a separate clarifier.
</Callout>

`IntentClarifier` analyzes a caller's intent and returns the subset of choices that could plausibly match, ordered by likelihood. Use this when an intent may be ambiguous and you need to surface options for the caller to confirm.

<CodeTabs
  python={{ code: INTENT_CLARIFIER_SIG_PY, filename: "signature" }}
  typescript={{ code: INTENT_CLARIFIER_SIG_TS, filename: "signature" }}
/>

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `intent_choices` | `list[str] \| dict[str, str]` | Yes | The set of intents to match against. Same format as `IntentRecognizer`. |
| `client` | `openai.OpenAI` | No | An OpenAI client to use. If omitted, a client is created automatically. |

**`propose_choices(intent: str) -> list[str]`** — Returns a list of choices that could match `intent`, ordered by likelihood:
- One element if the intent clearly maps to a single choice.
- Multiple elements if the intent is ambiguous.
- Empty list if the intent matches none of the provided choices.

An empty list means the caller's intent is out-of-scope — not that an error occurred. When `intent_choices` is a `dict`, only the keys appear in the returned list.

<CodeTabs
  python={{ code: INTENT_CLARIFIER_EX_PY, filename: "scheduler_agent.py" }}
  typescript={{ code: INTENT_CLARIFIER_EX_TS, filename: "scheduler_agent.ts" }}
/>

<AutoNextLink currentSection="intent-helpers" />


---

<!-- section: document-qa -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { CodeBlock } from '../views/docs/CodeBlock';
import { Callout, AutoNextLink } from '../views/docs/prose';
export const DOCUMENT_QA_SIG_PY = `from guava.helpers.rag import DocumentQA

DocumentQA(
    store=None,             # VectorStore for local mode; omit for server mode
    documents=None,         # str or list[str] — documents to index
    ids=None,               # list[str] — stable IDs for upsert/delete
    chunk_size=5000,        # max chars per chunk (local mode only)
    chunk_overlap=200,      # overlap between chunks (local mode only)
    instructions=None,      # system instruction override
    *,
    generation_model=None,  # GenerationModel (required for local mode)
    namespace=None,         # server-mode namespace for concurrent instances
)`;

export const DOCUMENT_QA_SIG_TS = `import { DocumentQA } from "@guava-ai/guava-sdk/helpers";

// Server mode only — local mode (VectorStore backends) is Python-only.
new DocumentQA({
  documents?,    // string | string[] — documents to index
  ids?,          // string[] — stable IDs for upsert/delete
  instructions?, // string — system instruction override
  namespace?,    // string — required for concurrent instances
})

await documentQA.ask(question: string): Promise<string>
await documentQA.upsertDocument(key: string, text: string): Promise<void>
await documentQA.addDocument(text: string): Promise<void>
await documentQA.deleteDocument(key: string): Promise<void>
await documentQA.clear(): Promise<void>`;

export const DOCUMENT_QA_EX_PY = `from guava.helpers.rag import DocumentQA

# Server mode (default) — documents stored and queried on Guava's server
qa = DocumentQA(documents=[policy_text, faq_text], namespace="policy_faq")
answer = qa.ask("What is the deductible?")

# Server mode — multiple concurrent instances (use namespace to isolate)
dental = DocumentQA(documents=dental_docs, namespace="dental")
restaurant = DocumentQA(documents=restaurant_docs, namespace="restaurant")
dental.ask("What is the copay?")       # only searches dental docs
restaurant.ask("Do you have vegan options?")  # only searches restaurant docs

# Local mode — Gemini (guava-sdk[genai])
from google import genai
from guava.helpers.lancedb import LanceDBStore
from guava.helpers.genai import GenAIEmbedding, GenAIGeneration

client = genai.Client(vertexai=True, project="my-project", location="us-central1")
store = LanceDBStore("gs://my-bucket/lancedb", embedding_model=GenAIEmbedding(client=client))
qa = DocumentQA(store=store, generation_model=GenAIGeneration(client=client))
qa.upsert_document("policy", my_text)
answer = qa.ask("What is the deductible?")

# Local mode — OpenAI (guava-sdk[openai])
import openai
from guava.helpers.lancedb import LanceDBStore
from guava.helpers.openai import OpenAIEmbedding, OpenAIGeneration

openai_client = openai.OpenAI()  # or AzureOpenAI / custom base_url
store = LanceDBStore("./lancedb_data", embedding_model=OpenAIEmbedding(client=openai_client))
qa = DocumentQA(store=store, generation_model=OpenAIGeneration(client=openai_client))
qa.upsert_document("policy", my_text)
answer = qa.ask("What is the deductible?")

# Wiring into an Agent
import guava
from guava import Agent

agent = Agent(name="Support", organization="Acme Corp", purpose="Answer customer questions.")
document_qa = DocumentQA(documents=some_text)

@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    return document_qa.ask(question)`;

export const DOCUMENT_QA_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { DocumentQA } from "@guava-ai/guava-sdk/helpers";

// Server mode — documents stored and queried on Guava's server
const qa = new DocumentQA({ documents: [policyText, faqText], namespace: "policy_faq" });
const answer = await qa.ask("What is the deductible?");

// Server mode — multiple concurrent instances (use namespace to isolate)
const dental = new DocumentQA({ documents: dentalDocs, namespace: "dental" });
const restaurant = new DocumentQA({ documents: restaurantDocs, namespace: "restaurant" });
await dental.ask("What is the copay?");            // only searches dental docs
await restaurant.ask("Do you have vegan options?"); // only searches restaurant docs

// Note: Local mode (LanceDB, ChromaDB, pgvector, Pinecone) is Python-only.

// Wiring into an Agent
const agent = new guava.Agent({
  name: "Support",
  organization: "Acme Corp",
  purpose: "Answer customer questions.",
});
const documentQA = new DocumentQA({ documents: [someText] });

agent.onQuestion(async (_call: guava.Call, question: string) => {
  return documentQA.ask(question);
})`;

export const DOCUMENT_QA_MGMT_EX_PY = `from guava.helpers.rag import DocumentQA

# Load initial documents with stable IDs
qa = DocumentQA(
    documents=[policy_v1, faq_v1, terms_v1],
    ids=["policy", "faq", "terms"],
    namespace="insurance",
)

# Later: policy was updated — replace it in-place
qa.upsert_document("policy", policy_v2)

# Add a new document without a pre-assigned ID
qa.add_document(new_bulletin_text)

# Remove a document that's no longer relevant
qa.delete_document("terms")

# Wipe everything and start fresh
qa.clear()`;

## DocumentQA

`DocumentQA` answers caller questions against documents using retrieval-augmented generation (RAG). It operates in one of two modes:

- **Server mode (default):** Documents are uploaded to the Guava server and questions are answered server-side. Intended for simple use cases with few documents.
- **Local mode:** Bring your own vector store and generation model for full control over the RAG pipeline. Guava provides ready-made backends for ChromaDB, LanceDB, pgvector, and Pinecone.

### Constructor

<CodeTabs
  python={{ code: DOCUMENT_QA_SIG_PY, filename: "signature" }}
  typescript={{ code: DOCUMENT_QA_SIG_TS, filename: "signature" }}
/>

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `store` | `VectorStore \| None` | No | `None` | Vector store for local mode. When omitted, server mode is used automatically. |
| `documents` | `list[str] \| str \| None` | No | `None` | Documents to index at construction time. Accepts a single string or a list. |
| `ids` | `list[str] \| None` | No | `None` | Caller-provided IDs for each document, enabling later `upsert_document` / `delete_document`. Length must match `documents` if provided. |
| `chunk_size` | `int` | No | `5000` | Maximum characters per chunk (local mode only). |
| `chunk_overlap` | `int` | No | `200` | Overlap between consecutive chunks in characters (local mode only). |
| `instructions` | `str \| None` | No | `None` | System instruction for the generation model. Overrides the built-in default. |
| `generation_model` | `GenerationModel \| None` | Local mode | `None` | Generation model for producing answers. Required when `store` is provided. |
| `namespace` | `str \| None` | Server mode | `None` | Stable string to scope this instance's documents on the server. |

<Callout>
  <span className="text-primary font-semibold">namespace requirement:</span> In server mode, `namespace` is required when running multiple `DocumentQA` instances concurrently — even across different files. Without a namespace, concurrent instances may interfere with each other's document stores.
</Callout>

### Methods

**`ask(question: str, k: int = 5) -> str`** — Retrieve relevant chunks and generate an answer. In server mode, `k` is ignored (the server uses full document context).

**`upsert_document(key: str, text: str) -> None`** — Add or replace a document by key. Stale chunks from a previously longer document are deleted automatically.

**`add_document(text: str) -> None`** — Add a document without specifying a key. In server mode, uses a content-derived key (SHA-256 hash).

**`delete_document(key: str) -> None`** — Delete a previously upserted document by key.

**`clear() -> None`** — Remove all documents from the store.

### Available VectorStore Backends (Local Mode)

| Class | Import | Install | Default Embedding |
|-------|--------|---------|-------------------|
| `ChromaVectorStore` | `guava.helpers.chromadb` | `pip install 'guava-sdk[chromadb]'` | Built-in `all-MiniLM-L6-v2` (no API needed) |
| `LanceDBStore` | `guava.helpers.lancedb` | `pip install 'guava-sdk[lancedb]'` | Required — pass an `EmbeddingModel` (`GenAIEmbedding`, `OpenAIEmbedding`, `PineconeInferenceEmbedding`, or a custom subclass) |
| `PgVectorStore` | `guava.helpers.pgvector` | `pip install 'guava-sdk[pgvector]'` | Required — pass an `EmbeddingModel` (`GenAIEmbedding`, `OpenAIEmbedding`, `PineconeInferenceEmbedding`, or a custom subclass) |
| `PineconeVectorStore` | `guava.helpers.pinecone` | `pip install 'guava-sdk[pinecone]'` | `multilingual-e5-large` via Pinecone Inference |

Embedding and generation provider extras: `pip install 'guava-sdk[genai]'` (Google Gemini) or `pip install 'guava-sdk[openai]'` (OpenAI). See the <a href="/docs/vector-stores">Vector Stores</a> reference for full constructor details and backend-specific options.

### Examples

<CodeTabs
  python={{ code: DOCUMENT_QA_EX_PY, filename: "document_qa_examples.py" }}
  typescript={{ code: DOCUMENT_QA_EX_TS, filename: "document_qa_examples.ts" }}
/>

### Incremental Document Management

Use `ids` to assign stable keys to documents at construction time, then use `upsert_document`, `delete_document`, and `clear` to manage documents without re-creating the `DocumentQA` instance.

<CodeBlock code={DOCUMENT_QA_MGMT_EX_PY} filename="document_management.py" language="python" />

<AutoNextLink currentSection="document-qa" />


---

<!-- section: datetime-filter -->

import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink } from '../views/docs/prose';
export const DATETIME_FILTER_SIG_PY = `from guava.helpers.openai import DatetimeFilter

DatetimeFilter(source_list: list[str], client: openai.OpenAI | None = None)
dt_filter.filter(query: str, max_results: int = 5) -> tuple[list[str], list[str]]`;

export const DATETIME_FILTER_SIG_TS = `import { DatetimeFilter } from "@guava-ai/guava-sdk/helpers/openai";

const dtFilter = new DatetimeFilter({ sourceList: string[] });
dtFilter.filter(query: string, maxResults?: number): Promise<[string[], string[]]>`;

export const DATETIME_FILTER_EX_PY = `from guava.helpers.openai import DatetimeFilter

AVAILABLE_SLOTS = [
    "2026-04-16T09:00:00",
    "2026-04-16T10:30:00",
    "2026-04-17T14:00:00",
    "2026-04-18T09:00:00",
]

dt_filter = DatetimeFilter(source_list=AVAILABLE_SLOTS)

matches, suggestions = dt_filter.filter("tomorrow morning", max_results=3)
# matches     == ["2026-04-16T09:00:00", "2026-04-16T10:30:00"]
# suggestions == []  (not needed — matches were found)

matches, suggestions = dt_filter.filter("this Friday at noon", max_results=3)
# matches     == []  (no Friday noon slot exists)
# suggestions == ["2026-04-17T14:00:00", ...]  (nearby alternatives offered)`;

export const DATETIME_FILTER_EX_TS = `import { DatetimeFilter } from "@guava-ai/guava-sdk/helpers/openai";

const AVAILABLE_SLOTS = [
  "2026-04-16T09:00:00",
  "2026-04-16T10:30:00",
  "2026-04-17T14:00:00",
  "2026-04-18T09:00:00",
];

const dtFilter = new DatetimeFilter({ sourceList: AVAILABLE_SLOTS });

const [matches, suggestions] = await dtFilter.filter("tomorrow morning", 3);
// matches     == ["2026-04-16T09:00:00", "2026-04-16T10:30:00"]
// suggestions == []  (not needed — matches were found)`;

export const DATETIME_FILTER_FIELD_EX_PY = `import guava
from guava import Agent
from guava.helpers.openai import DatetimeFilter

agent = Agent(
    name="Scheduler",
    organization="Acme Corp",
    purpose="Help callers schedule appointments.",
)

datetime_filter = DatetimeFilter(source_list=AVAILABLE_SLOTS)

@agent.on_call_start
def on_call_start(call: guava.Call):
    call.set_task(
        "schedule_appointment",
        checklist=[
            guava.Field(
                key="appointment_time",
                field_type="calendar_slot",
                description="Find a time that works for the caller",
                searchable=True,
            ),
        ],
    )

@agent.on_search_query("appointment_time")
def search_appointments(call: guava.Call, query: str):
    return datetime_filter.filter(query, max_results=3)`;

export const DATETIME_FILTER_FIELD_EX_TS = `import * as guava from "@guava-ai/guava-sdk";
import { DatetimeFilter } from "@guava-ai/guava-sdk/helpers/openai";

const agent = new guava.Agent({
  name: "Scheduler",
  organization: "Acme Corp",
  purpose: "Help callers schedule appointments.",
});

const datetimeFilter = new DatetimeFilter({ sourceList: AVAILABLE_SLOTS });

agent.onCallStart(async (call: guava.Call) => {
  await call.setTask({
    taskId: "schedule_appointment",
    checklist: [
      guava.Field({
        key: "appointment_time",
        fieldType: "calendar_slot",
        description: "Find a time that works for the caller",
        searchable: true,
      }),
    ],
  });
});

agent.onSearchQuery("appointment_time", async (_call, query) => {
  return datetimeFilter.filter(query, { maxResults: 3 });
})`;

## DatetimeFilter

`DatetimeFilter` filters a list of ISO 8601 datetime strings to find entries matching a natural-language query (e.g. "tomorrow afternoon"). Returns both matching datetimes and fallback suggestions when no exact match exists.

### Constructor

<CodeTabs
  python={{ code: DATETIME_FILTER_SIG_PY, filename: "signature" }}
  typescript={{ code: DATETIME_FILTER_SIG_TS, filename: "signature" }}
/>

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_list` | `list[str]` | Yes | The pool of available appointment datetimes in ISO 8601 format (e.g. `"2026-03-02T09:00:00"`). The model will only return values present in this list. |
| `client` | `openai.OpenAI` | No | An OpenAI client to use. If omitted, a client is created automatically. |

### Methods

**`filter(query: str, max_results: int = 5) -> tuple[list[str], list[str]]`**

Returns a 2-tuple `(matching_appointments, other_appointments)`:
- `matching_appointments`: datetimes from `source_list` that match `query`, capped at `max_results`.
- `other_appointments`: alternative datetimes to suggest when `matching_appointments` is empty, also capped at `max_results`.

### Edge Cases

- Raises `AssertionError` if `max_results` is not an `int`.
- Both output lists are guaranteed to contain only values drawn from `source_list` — the model is explicitly instructed never to hallucinate datetimes.
- Today's date is injected into the prompt automatically, so relative queries like "tomorrow" and "next week" resolve correctly without any date math on the caller's side.
- `other_appointments` may be non-empty even when `matching_appointments` is empty — use it to offer the caller nearby alternatives.

<Callout>
  <span className="text-primary font-semibold">Model details:</span> `DatetimeFilter` uses `gpt-5-mini` with `reasoning.effort = "medium"`. These settings are not configurable.
</Callout>

### Basic Usage

<CodeTabs
  python={{ code: DATETIME_FILTER_EX_PY, filename: "datetime_filter.py" }}
  typescript={{ code: DATETIME_FILTER_EX_TS, filename: "datetime_filter.ts" }}
/>

### Using with `Field` and `on_search_query`

A common pattern is to pair `DatetimeFilter` with a `Field` of type `"calendar_slot"` with `searchable=True`, and wire the filter into the `on_search_query` callback:

<CodeTabs
  python={{ code: DATETIME_FILTER_FIELD_EX_PY, filename: "scheduling_agent.py" }}
  typescript={{ code: DATETIME_FILTER_FIELD_EX_TS, filename: "scheduling_agent.ts" }}
/>

<AutoNextLink currentSection="datetime-filter" />


---

<!-- section: vector-stores -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { Callout, AutoNextLink } from '../views/docs/prose';
export const VECTOR_STORES_EX_PY = `from guava.helpers.rag import DocumentQA
from guava.helpers.genai import GenAIEmbedding, GenAIGeneration
from google import genai

client = genai.Client(vertexai=True, project="my-project", location="us-central1")
embedding = GenAIEmbedding(client=client)   # gemini-embedding-001, 768-dim
generation = GenAIGeneration(client=client)  # gemini-2.5-flash


# ChromaDB — no external embedding API required; persists to disk by default
from guava.helpers.chromadb import ChromaVectorStore

store = ChromaVectorStore()                     # path="./chroma_data" by default
store = ChromaVectorStore(path=None)            # in-memory/ephemeral

qa = DocumentQA(store=store, generation_model=generation, documents=[doc1, doc2])
answer = qa.ask("What is the deductible?")


# LanceDB — local path or GCS URI; requires an embedding model
from guava.helpers.lancedb import LanceDBStore

store = LanceDBStore("./lancedb_data", embedding_model=embedding)
store = LanceDBStore("gs://my-bucket/lancedb", embedding_model=embedding)  # GCS

qa = DocumentQA(store=store, generation_model=generation, documents=[doc1, doc2])
answer = qa.ask("What is the deductible?")


# pgvector — Postgres connection string; table and indexes created automatically
from guava.helpers.pgvector import PgVectorStore

store = PgVectorStore(
    db_url="postgresql://user:password@localhost:5432/mydb",
    embedding_model=embedding,
)
qa = DocumentQA(store=store, generation_model=generation, documents=[doc1, doc2])
answer = qa.ask("What is the deductible?")


# Pinecone — set PINECONE_API_KEY; index and embeddings are fully managed
from guava.helpers.pinecone import PineconeVectorStore

store = PineconeVectorStore()                   # index_name="guava-chunks" by default

qa = DocumentQA(store=store, generation_model=generation, documents=[doc1, doc2])
answer = qa.ask("What is the deductible?")`;

## Vector Stores

Guava provides four ready-made `VectorStore` implementations that can be passed directly to `DocumentQA` as the `store` argument. Each wraps a popular vector database and handles embedding, indexing, and similarity search.

<Callout>
  <span className="text-primary font-semibold">Python only:</span> Vector store backends are currently available in Python only. TypeScript equivalents are not yet available.
</Callout>

### Installation

Install only the backend(s) you need:

- `pip install 'guava-sdk[chromadb]'`
- `pip install 'guava-sdk[lancedb]'`
- `pip install 'guava-sdk[pgvector]'`
- `pip install 'guava-sdk[pinecone]'`

Embedding and generation provider extras:

- `pip install 'guava-sdk[genai]'` — Google Gemini (backs `GenAIEmbedding` / `GenAIGeneration`)
- `pip install 'guava-sdk[openai]'` — OpenAI (backs `OpenAIEmbedding` / `OpenAIGeneration`)

Importing a backend class without the corresponding extra installed raises `ImportError` with an install hint.

### ChromaVectorStore

`from guava.helpers.chromadb import ChromaVectorStore`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `str \| None` | No | `"./chroma_data"` | Directory for persistent storage. Pass `None` for an in-memory ephemeral store. |
| `collection_name` | `str` | No | `"chunks"` | ChromaDB collection name. |
| `embedding_model` | `EmbeddingModel \| None` | No | `None` | External embedding model. When omitted, ChromaDB's built-in `all-MiniLM-L6-v2` model is used — no external API needed. |

### LanceDBStore

`from guava.helpers.lancedb import LanceDBStore`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `str` | No | `"./lancedb_data"` | Local path or GCS URI (e.g. `"gs://bucket/lancedb"`) for storage. |
| `table_name` | `str` | No | `"chunks"` | LanceDB table name. |
| `embedding_model` | `EmbeddingModel` | **Yes** | — | Embedding model to use. Pass a configured instance such as `GenAIEmbedding` or `OpenAIEmbedding`. |

<Callout>
  <span className="text-primary font-semibold">Note:</span> LanceDB silently drops tables that predate the current schema version. This triggers a full re-index the next time `DocumentQA` ingests documents.
</Callout>

### PgVectorStore

`from guava.helpers.pgvector import PgVectorStore`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `db_url` | `str` | **Yes** | — | PostgreSQL connection string (e.g. `"postgresql://user:pass@host/db"`). |
| `table_name` | `str` | No | `"guava_chunks"` | Table name for stored chunks. |
| `embedding_model` | `EmbeddingModel` | **Yes** | — | Embedding model to use. Pass a configured instance such as `GenAIEmbedding` or `OpenAIEmbedding`. |

`PgVectorStore` creates the `vector` extension, chunks table, and HNSW cosine index automatically on first connect. If the connecting user lacks `CREATE EXTENSION` privileges, initialization will fail.

<Callout>
  <span className="text-primary font-semibold">Managed Postgres:</span> Managed services (Cloud SQL, AlloyDB, RDS) are untested but expected to work since the implementation uses standard `psycopg`.
</Callout>

### PineconeVectorStore

`from guava.helpers.pinecone import PineconeVectorStore`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `api_key` | `str \| None` | No | env `PINECONE_API_KEY` | Pinecone API key. If omitted, reads from the environment. |
| `index_name` | `str` | No | `"guava-chunks"` | Pinecone index name. Created automatically if it does not exist. |
| `cloud` | `str` | No | `"aws"` | Serverless cloud provider for index creation. Ignored if the index already exists. |
| `region` | `str` | No | `"us-east-1"` | Serverless region for index creation. Ignored if the index already exists. |
| `embedding_model` | `EmbeddingModel \| None` | No | `PineconeInferenceEmbedding` | Defaults to `multilingual-e5-large` (1024-dim) via Pinecone's hosted Inference API. |

<Callout>
  <span className="text-primary font-semibold">Cold start:</span> Pinecone index creation can take 30–60 seconds on first use. Subsequent instantiations with the same `index_name` skip creation and connect immediately.
</Callout>

### PineconeInferenceEmbedding

`from guava.helpers.pinecone import PineconeInferenceEmbedding`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pc` | `Pinecone` | **Yes** | — | A configured `Pinecone` client instance. |
| `model` | `str` | No | `"multilingual-e5-large"` | Pinecone inference model name. |
| `dimensionality` | `int` | No | `1024` | Output vector size. |

### GenAIEmbedding / GenAIGeneration

`from guava.helpers.genai import GenAIEmbedding, GenAIGeneration`

Install: `pip install 'guava-sdk[genai]'`

**GenAIEmbedding** — `EmbeddingModel` backed by Google Gemini. Works with either a Vertex AI client (`genai.Client(vertexai=True, project=..., location=...)`) or an AI Studio client (`genai.Client(api_key=...)`).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client` | `google.genai.Client` | **Yes** | — | Configured Gemini client. |
| `model` | `str` | No | `"gemini-embedding-001"` | Gemini embedding model name. |
| `dimensionality` | `int` | No | `768` | Output vector size. |

Uses different task types under the hood: `RETRIEVAL_DOCUMENT` for `embed_documents` and `QUESTION_ANSWERING` for `embed_query`, which improves retrieval quality versus a single generic embedding.

**GenAIGeneration** — `GenerationModel` backed by Google Gemini.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client` | `google.genai.Client` | **Yes** | — | Configured Gemini client. |
| `model` | `str` | No | `"gemini-2.5-flash"` | Gemini chat model name. |
| `thinking_budget` | `int \| None` | No | `0` | Token budget for the model's internal thinking step. Default `0` disables thinking on `gemini-2.5-flash` for faster responses. Pass `None` for non-thinking models (e.g. `gemini-1.5-flash`). Pass a positive integer (e.g. `8192`) to enable extended thinking. |

<Callout>
  <span className="text-primary font-semibold">thinking_budget compatibility:</span> The default `thinking_budget=0` works with `gemini-2.5-flash`. If you switch to a non-thinking model like `gemini-1.5-flash`, pass `thinking_budget=None` — that model raises an error when it receives a `thinking_config`.
</Callout>

### OpenAIEmbedding / OpenAIGeneration

`from guava.helpers.openai import OpenAIEmbedding, OpenAIGeneration`

Install: `pip install 'guava-sdk[openai]'`

The caller supplies a configured `openai.OpenAI` instance. The same wrappers work against Azure OpenAI or any OpenAI-compatible base URL — the client object decides where requests go.

**OpenAIEmbedding** — `EmbeddingModel` backed by the OpenAI Embeddings API.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client` | `openai.OpenAI` | **Yes** | — | Configured OpenAI client. |
| `model` | `str` | No | `"text-embedding-3-small"` | OpenAI embedding model name. |
| `dimensionality` | `int` | No | `1536` | Output vector size. |

**OpenAIGeneration** — `GenerationModel` backed by OpenAI `chat.completions`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client` | `openai.OpenAI` | **Yes** | — | Configured OpenAI client. |
| `model` | `str` | No | `"gpt-5-mini"` | OpenAI chat model name. |

The `system_instruction` argument to `generate()` is mapped to a `{"role": "system", ...}` message prepended to the user prompt.

### GenerationModel

Any implementation of the `guava.helpers.rag.GenerationModel` interface works with `DocumentQA` in local mode. The examples on this page use `GenAIGeneration`, but `OpenAIGeneration` (above) or any custom `GenerationModel` subclass works equally well.

### Examples

<CodeBlock code={VECTOR_STORES_EX_PY} filename="vector_store_examples.py" language="python" />

<AutoNextLink currentSection="vector-stores" />


---

<!-- section: campaign -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { LanguageTabs, LanguageAlternate } from '../views/docs/CodeTabs';
import { Callout, Prose, AutoNextLink } from '../views/docs/prose';

## Outbound Campaigns

While you can use <LanguageAlternate pythonContent={<code>agent.call_phone("+1...")</code>} typescriptContent={<code>agent.callPhone("+1...")</code>} /> to place singular outbound calls, we recommend using Campaigns when calling multiple contacts.

Campaigns automatically manage missed-call retries, enforce calling windows, and control call concurrency.
Since they are persistent resources, you should create one Campaign for each distinct use case and continue adding contacts to it as needed.

While Campaigns are responsible for dispatching calls - you will still need to "attach" an Agent to handle the call itself - this is done using a unique "code" created for each Campaign.

<Callout>
  Prefer to manage campaigns programmatically over HTTP? See the <a href="/docs/campaigns-api">Campaigns API</a> reference for the full set of REST endpoints — create, upload contacts, status, and more.
</Callout>

## Before you start

You'll need:

- **A Guava account** — sign up at [app.goguava.ai](https://app.goguava.ai)
- **A phone number** — from the [Phone Numbers](https://app.goguava.ai/dashboard/phone-numbers) page
- **Outbound permission** — outbound dialing requires approval. See [Outbound & SMS Compliance](./outbound-and-sms-permissions) for the required registrations, then fill out the **Outbound Dialing Permissions Request** form on the [Compliance](https://app.goguava.ai/dashboard/compliance) page.

## Create a campaign in the dashboard

Open the [Campaigns](https://app.goguava.ai/dashboard/campaigns) page and click **Create Campaign**. Configure your campaign name, origin phone numbers, calling windows, and retry settings.

Once created, take note of the campaign code — it starts with `gcmp-...`.

## Upload contacts

From the campaign's detail page in the dashboard, upload your contact list. Each contact needs a phone number and any per-call data variables your agent will use (such as a patient name or appointment time).

These variables will be accessible inside your agent callbacks via <LanguageAlternate pythonContent={<code>call.get_variable()</code>} typescriptContent={<code>call.getVariable()</code>} />.

## Write your agent

Define an `Agent` and attach callbacks for each stage of the call.

export const AGENT_PY = `import guava
from guava import Agent, Field

agent = Agent(
    name="Sarah",
    organization="Valley Dental",
    purpose="Remind patients about their upcoming dental appointments.",
)

# Fires at the start of every call. We'll start by using reach_person()
# to confirm we're talking to the right person.
@agent.on_call_start
def on_call_start(call: guava.Call):
    call.reach_person(
        contact_full_name=call.get_variable("patient_name"),
    )

# Fires once reach_person() resolves. outcome="available" means the contact answered.
@agent.on_reach_person
def on_reach_person(call: guava.Call, outcome: str):
    if outcome == "available":
        # Appointment details are only loaded into the context after the
        # caller's identity has been confirmed.
        call.add_info("appointment_details", {
            "patient_name": call.get_variable("patient_name"),
            "appointment_date": call.get_variable("appointment_date"),
            "appointment_time": call.get_variable("appointment_time")
        })

        call.set_task(
            "confirm_appointment",
            objective="Confirm the appointment date and time.",
            checklist=[
                Field(
                    key="appointment_response",
                    description="Whether the patient confirms, reschedules, or cancels",
                    field_type="multiple_choice",
                    choices=["confirmed", "reschedule", "cancel"],
                ),
            ],
        )
    else:
        call.hangup()

# Fires when all checklist items are resolved.
@agent.on_task_complete("confirm_appointment")
def on_confirmed(call: guava.Call):
    call.hangup("Thank them and end the call.")`;

export const AGENT_TS = `import * as guava from "@guava-ai/guava-sdk";

const agent = new guava.Agent({
  name: "Sarah",
  organization: "Valley Dental",
  purpose: "Remind patients about their upcoming dental appointments.",
});

// Fires at the start of every call. We'll start by using reachPerson()
// to confirm we're talking to the right person.
agent.onCallStart(async (call: guava.Call) => {
  await call.reachPerson(await call.getVariable("patient_name"));
});

// Fires once reachPerson() resolves. outcome="available" means the contact answered.
agent.onReachPerson(async (call: guava.Call, outcome: string) => {
  if (outcome === "available") {
    // Appointment details are only loaded into the context after the
    // caller's identity has been confirmed.
    await call.addInfo("appointment_details", {
      patient_name: await call.getVariable("patient_name"),
      appointment_date: await call.getVariable("appointment_date"),
      appointment_time: await call.getVariable("appointment_time"),
    });

    await call.setTask({
      taskId: "confirm_appointment",
      objective: "Confirm the appointment date and time.",
      checklist: [
        guava.Field({
          key: "appointment_response",
          description: "Whether the patient confirms, reschedules, or cancels",
          fieldType: "multiple_choice",
          choices: ["confirmed", "reschedule", "cancel"],
        }),
      ],
    });
  } else {
    await call.hangup();
  }
});

// Fires when all checklist items are resolved.
agent.onTaskComplete("confirm_appointment", async (call) => {
  await call.hangup("Thank them and end the call.");
});`;

<LanguageTabs
  pythonContent={<CodeBlock code={AGENT_PY} filename="campaign.py" language="python" />}
  typescriptContent={<CodeBlock code={AGENT_TS} filename="campaign.ts" language="typescript" />}
/>

export const TEST_PY = `agent.chat(variables={
    "patient_name": "Jane Smith",
    "appointment_date": "Monday, June 23rd",
    "appointment_time": "2:00 PM",
})`;

export const TEST_TS = `await agent.chat({
  patient_name: "Jane Smith",
  appointment_date: "Monday, June 23rd",
  appointment_time: "2:00 PM",
});`;

## Test your agent

<LanguageTabs
  pythonContent={<><Prose>Before attaching to a campaign, test your agent using <code>agent.call_local()</code> or <code>agent.chat()</code>. Pass a <code>variables</code> dict to simulate per-contact data:</Prose><CodeBlock code={TEST_PY} filename="campaign.py" language="python" /></>}
  typescriptContent={<><Prose>Before attaching to a campaign, test your agent using <code>agent.callLocal()</code> or <code>agent.chat()</code>. Pass a <code>variables</code> object to simulate per-contact data:</Prose><CodeBlock code={TEST_TS} filename="campaign.ts" language="typescript" /></>}
/>

export const ATTACH_PY = `agent.attach_campaign(campaign_code="gcmp-...")`;

export const ATTACH_TS = `await agent.attachCampaign("gcmp-...");`;

## Attach and serve the campaign

<LanguageTabs
  pythonContent={<><Prose>Next, run <code>agent.attach_campaign("gcmp-...")</code>. This "attaches" your agent to the Campaign that we previously created.</Prose><CodeBlock code={ATTACH_PY} filename="campaign.py" language="python" /></>}
  typescriptContent={<><Prose>Next, call <code>await agent.attachCampaign("gcmp-...")</code>. This "attaches" your agent to the Campaign that we previously created.</Prose><CodeBlock code={ATTACH_TS} filename="campaign.ts" language="typescript" /></>}
/>

## Review calls in the dashboard

Once your campaign is running, visit the [Campaigns](https://app.goguava.ai/dashboard/campaigns) page to monitor progress.

<AutoNextLink currentSection="campaign" />


---

<!-- section: sip-integrations -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { CodeTabs } from '../views/docs/CodeTabs';
import { Callout, AutoNextLink, Prose, PropTable } from '../views/docs/prose';


## SIP Integrations

Guava agents can receive inbound calls over the SIP protocol. You can use this feature to directly dial Guava agents from an SBC, PBX, or softphone without going out to the PSTN.

<Callout>
<strong>Using Twilio?</strong> See the [Twilio Programmable Voice guide](/docs/twilio-programmable-voice) or the [Twilio Elastic SIP guide](/docs/twilio-elastic-sip) for step-by-step walkthroughs.
</Callout>

### Contact us for peer whitelisting

Currently, we are whitelisting SIP peers at our firewall level. Contact us at [hi@goguava.ai](mailto:hi@goguava.ai) to get your source IPs whitelisted.

### Check connectivity

Once whitelisted, try to make an `OPTIONS` ping to our SIP trunk at `sip.goguava.ai`. If the check fails, see our guide below on firewall configuration.

### Create a SIP code

Every SIP integration requires a `guavasip` code, which you can create in the Guava dashboard. `guavasip` codes work just like registered phone numbers — agents can listen to them and peers can dial them.

1. Open the [SIP page in the dashboard](https://app.goguava.ai/dashboard/sip).
2. Click **Create SIP Code**.
3. Take note of both the SIP code and the termination URI.

<CodeBlock
  language="bash"
  code={`# You will see a SIP code like this.
guavasip-xxx

# Your termination URI will look like this.
sip:guavasip-xxx@sip.goguava.ai`}
/>

### Attach your agent to the SIP code

Next, start an agent using `agent.listen_sip("guavasip-xxx")`. This is the SIP equivalent of `agent.listen_phone(...)` — Guava forwards every call addressed to that code to your agent.

<CodeBlock
  filename="main.py"
  language="python"
  code={`import os
import guava

agent = guava.Agent(
    name="Nova",
    organization="Acme Corp",
    purpose="Handle inbound calls from the corporate PBX.",
)

# Register handlers — on_call_received, on_call_start, etc.

# Replace with your SIP code from the dashboard.
agent.listen_sip("guavasip-xxx")`}
/>

<Callout>To connect an agent to both a phone number and a SIP code simultaneously, see the documentation for [guava.Runner](./runner).</Callout>

### Dial your agent

The last step is to dial your agent using the termination URI (e.g. `sip:guavasip-xxx@sip.goguava.ai`). If you're having trouble connecting to your agent, please contact us at [hi@goguava.ai](mailto:hi@goguava.ai).

### Firewall configuration

To dial our SIP trunk from your network, you may need to whitelist us in your firewall.

|     |  |
| -------- | ------- |
| **FQDN**  | The FQDN for the Guava SIP trunk is `sip.goguava.ai`.    |
| **Trunk IP** | The IP address for the Guava SIP trunk is `136.118.29.109`. This IP is used for both media and signaling.     |
| **TCP Ports**    | `5060`, `5061` (TLS)   |
| **UDP Ports** | `5060`, `10000-65535` (Media) |
| **ICMP** | Whitelist ICMP to allow connectivity checks (e.g. `ping`). |
| **Supported Codecs** | `PCMU` (G.711 μ-law), `PCMA` (G.711 a-law) |

<AutoNextLink currentSection="sip-integrations" />


---

<!-- section: twilio-programmable-voice -->

import { CodeBlock } from '../views/docs/CodeBlock';
import { Callout, AutoNextLink, Prose, PropTable } from '../views/docs/prose';

## Twilio Programmable Voice (TwiML)

<Callout><strong>Looking for Twilio Elastic SIP?</strong> Check out our [guide here](./twilio-elastic-sip).</Callout>

If you already use Twilio Programmable Voice / TwiML, you can transfer to a Guava agent at any time during your call.

1. Create a Guava SIP code "guavasip-xxx" [on the Guava dashboard](https://app.goguava.ai/dashboard/sip).
2. Attach an agent to the SIP code.
3. Use the following TwiML template to transfer to your agent.

<CodeBlock
  language="xml"
  code={`<Response>
    <Dial>
      <Sip>sip:guavasip-xxx@sip.goguava.ai</Sip>
    </Dial>
</Response>`}
/>

Below is a more detailed guide.

### Create a Guava SIP code

Every SIP integration in Guava requires a `guavasip` code. `guavasip` codes are used to route inbound calls to agents — agents can listen to codes and peers dial them.

Open the [SIP page in the Guava dashboard](https://app.goguava.ai/dashboard/sip) and click **Create SIP Code**.

<p style={{display: "flex", justifyContent: "center", margin: "1.5rem 0"}}>
    <img style={{maxWidth: "700px", width: "100%", borderRadius: "6px"}} src="/docs/sip-dashboard.png" alt="Guava SIP dashboard" />
</p>

Take note of the SIP code and the termination URI.


### Start an agent

Next, start an agent using `agent.listen_sip("guavasip-xxx")` — Guava forwards every call addressed to that code to your agent.

<CodeBlock
  filename="main.py"
  language="python"
  code={`import os
import guava

agent = guava.Agent(
    name="Nova",
    organization="Acme Corp",
)

# Register handlers — on_call_received, on_call_start, etc.

# Replace with your SIP code from the dashboard.
agent.listen_sip("guavasip-xxx")`}
/>


### Twilio Example: Outbound Call

Initiate an outbound call through Twilio, then use a `Dial` command to transfer the call to your Guava agent using the termination URI.

<CodeBlock
  filename="twilio_outbound.py"
  language="python"
  code={`import os
from twilio.rest import Client

client = Client(
    os.environ["TWILIO_ACCOUNT_SID"],
    os.environ["TWILIO_AUTH_TOKEN"]
)

client.calls.create(
    to="+1...", # The recipient of the call.
    from_="+1...", # Your owned Twilio number.
    twiml="<Response><Dial><Sip>sip:guavasip-xxx@sip.goguava.ai</Sip></Dial></Response>",
)`}
/>

<AutoNextLink currentSection="twilio-programmable-voice" />


---

## Additional Documentation

The following pages are not included in this starter kit but are available in the full documentation:

- [Overview](https://goguava.ai/docs/api-overview.md)
- [Campaigns API](https://goguava.ai/docs/campaigns-api.md)
- [Conversations](https://goguava.ai/docs/conversations-api.md)
- [Messages](https://goguava.ai/docs/messages-api.md)
- [WebRTC Widgets Overview](https://goguava.ai/docs/webrtc-widgets.md)
- [Base44](https://goguava.ai/docs/base44-guide.md)
- [Lovable](https://goguava.ai/docs/lovable-guide.md)
- [Agent Testing](https://goguava.ai/docs/agent-testing.md)
- [Agentic Tenacity](https://goguava.ai/docs/agentic-tenacity.md)
- [Deployment](https://goguava.ai/docs/deployment.md)
- [CLI Reference](https://goguava.ai/docs/cli-reference.md)
- [Outbound & SMS Compliance](https://goguava.ai/docs/outbound-and-sms-permissions.md)
- [Phone Number Trust & Reputation](https://goguava.ai/docs/phone-number-trust-reputation.md)
- [Heroku](https://goguava.ai/docs/deploy-heroku.md)
- [Twilio Elastic SIP](https://goguava.ai/docs/twilio-elastic-sip.md)
- [Cisco CUBE / CUCM](https://goguava.ai/docs/cisco-cube-cucm.md)
- [AI Customer Service](https://goguava.ai/docs/amazon-connect-ai-customer-service.md)
- [Appointment Reminder](https://goguava.ai/docs/amazon-connect-appointment-reminder.md)
- [CSAT Survey](https://goguava.ai/docs/amazon-connect-csat-survey.md)
- [Product Support](https://goguava.ai/docs/amazon-connect-product-support.md)
- [Release Notes](https://goguava.ai/docs/release-notes.md)