# REQ-1-1: Service Specification

## Overview

This service exposes a Python-based API that integrates **Clerk.com**
for authentication, **Gemini 2.5** for NLP processing, and a per-user
token management system.

## Core Responsibilities

### 1. Session Validation with Clerk.com

All requests must include a valid Clerk-issued token.\
The service verifies that the user is authenticated before processing
any operation.

### 2. Request Handling and NLP Processing

-   Receives `input_text` from a web-based chat interface, along with
    the Clerk token.
-   Processes content using **Gemini 2.5**.
-   Responses are rendered using **Jinja2** templates to ensure
    consistent formatting.

### 3. Token Quota Validation

-   Each request checks the user's available tokens.
-   If the user approaches the threshold defined in the `.env`, a
    warning is returned.
-   If insufficient tokens are available, the request is rejected with
    the corresponding error.

### 4. Token Deduction per Request

-   Upon successful processing, tokens consumed by Gemini are deducted
    from the user's quota.

## Endpoints

### `GET /health`

Returns the system health status and service version.

### `POST /v1/demo`

-   Validates session via Clerk JWT.
-   Verifies token quota.
-   Processes the input text with Gemini 2.5 via Vertex AI SDK.
-   Deducts tokens consumed from user's quota.
-   Returns the generated response.

### `GET /v1/demo/status`

Displays the user's available tokens and consumption metrics.
Requires Clerk JWT authentication.

### `GET /v1/demo/history`

Returns the user's chat history with pagination support.
Requires Clerk JWT authentication.
