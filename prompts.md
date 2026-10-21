# Prompts behind Action Trainer

This is a chronological summary of the user prompts that led to this
repository, from the initial badge experiment through extracting the trainer
and adding agent instructions. It is not a verbatim transcript. Quoted
excerpts are original wording; the surrounding text summarizes intent.

## 1. Plan the end-to-end experiment

> Pull down the latest from upstream. Then I want you to use Opus + Astra to
> help come up with a plan.

The initial request was to collect accelerometer data from a Universe badge
over Bluetooth and record training examples for four actions: **Throw,
Still, Drop, and Walk**, with roughly ten examples of each.

The requested workflow was:

- Record labelled sessions in a laptop application and train a classifier.
- Deploy the trained model to a MicroPython badge app.
- Show the detected action as text, with a different background colour for
  each action.
- Broadcast detected actions to a separate laptop application that shows
  multiple named badges and plays sounds for events.
- Track which badge stays airborne longest, reset air time after at least
  three seconds of Still, and keep a score for each drop.

The user asked for a plan, clarification points before implementation, and
an editable Markdown canvas for feedback.

## 2. Incorporate feedback and existing BLE examples

> Answered the questions. I've just pulled down some bluetooth based apps
> into the 'Extract badge apps' session - you'll want to look at those and
> see how the BLE plan might need adjusting.

The plan was to be revised using the user's answers and the newly available
Bluetooth app examples, rather than assuming a BLE design without checking
the badge's existing implementations.

## 3. Choose a real-hardware MVP

> Whats the best way of doing an MVP test with the real badge connected?

The user suggested testing BLE communications first, then training a
classifier and pushing it to the badge. They also proposed Web Serial for
pushing or updating the model's Python file.

> ok cool - lets do the first phase. Badge is connected

This moved the work from planning to probing the connected badge and testing
the communication path.

## 4. Clarify the classifier and untethered test workflow

> What model are we using for the classifier

The user asked which classifier would be used. The eventual training pipeline
in this repository uses a small decision tree that exports to standalone
MicroPython code; the early badge tests used a physics-based detector.

> What's next?

> Will I be able to run that command and then unplug the badge from the USB
> so I can walk?

The user wanted the next concrete test and confirmation that the badge could
run untethered for movement trials.

> Run the python command for me

This asked the agent to execute the test rather than only provide commands.

## 5. Iterate with the connected badge

The user supplied short confirmations to advance the hardware testing:

> Done screen showing - badge plugged back in

> go

> Seems to be doing a pretty good job. Reconnected the badge

These prompts supported the live deploy, disconnect, physical-test, and
reconnect loop. The work progressed to a BLE recording mode and a local
browser-based recorder.

> pausing for now to sleep

> Badge plugged in - resume

The user paused the experiment and later resumed with a badge connected.
These were session-control prompts, not new product requirements.

## 6. Extract the laptop trainer into its own repository

> Right - let's pull out the training application into a seperate repo in
> my martinwoodward org (martinwoodward/action-trainer). When trained it will
> create the model that is used by a pedometer app in the badger/home repo

This established the repository boundary:

- **`martinwoodward/action-trainer`** owns the laptop recorder, labelled
  session format, training pipeline, and generated `model.py`.
- **`badger/home`** owns the badge app that consumes the model, including
  badge-side integration and deployment.

## 7. Make Still the default detected action

> Instead of 'Unkown' default to 'Still' as the detected action.

The generated model must return **Still** instead of **Unknown** as its
fallback detected action. The implementation retains `unknown` as a useful
training label but maps learned Unknown predictions and empty windows to
`still`.

## 8. Carry badge-development instructions into the new repository

> Make sure the copilot instructions are in that repo too so that it knows
> how to connect to teh badge and develop and deploy apps to it.

The new repository needed agent instructions covering badge discovery and
serial-port ownership, the Universe 2026 runtime APIs, development and
deployment workflows, and the boundary with `badger/home`. This resulted in
the root `AGENTS.md`, `.github/copilot-instructions.md`, and mirrored badge,
USB serial, and hardware guides in `docs/badge/`.

## 9. Preserve the prompt history

> Can you summarize the prompts that I did to get here into a prompts.md
> file in the actions-trainer repo?

This document records that progression in the existing
`martinwoodward/action-trainer` repository.

## Scope at this point

The repository contains the laptop recorder, BLE listener and protocol,
decision-tree training/export pipeline, and badge-development instructions.
The initial real-badge communication tests and physics-based detector
preceded this extraction.

The original end-to-end vision is broader than the completed trainer:
real labelled training sessions, validation of a model trained on those
sessions, badge-side pedometer integration, automated Web Serial model
updates, and the multi-badge sound/air-time dashboard remain follow-on work.
Their appearance in the prompts above is not a claim that they are already
implemented.
