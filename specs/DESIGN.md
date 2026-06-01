---
version: 1.0
name: AWS-Invoice-Intelligence-Design-System
description: Modern AWS-inspired design system for the Invoice Intelligence Platform. Combines AWS enterprise aesthetics, cloud-native architecture visuals, analytics dashboards, and GenAI interactions. Designed for React + Vite applications deployed on AWS serverless infrastructure.

colors:
  primary: "#232F3E"
  primary-deep: "#161E2A"
  on-primary: "#FFFFFF"

  accent: "#FF9900"
  accent-light: "#FFB84D"

  ai-accent: "#7B61FF"
  ai-accent-soft: "#EDE8FF"

  success: "#2E8540"
  warning: "#FFB84D"
  error: "#D13212"

  background: "#F8F9FB"
  surface: "#FFFFFF"
  surface-soft: "#EEF1F5"

  text-primary: "#1A1A1A"
  text-secondary: "#5F6B7A"
  text-muted: "#8A94A6"

  border: "#D5DBE3"

design_principles:
  - AWS-inspired
  - Cloud-native
  - Analytics-first
  - Architecture-driven
  - Enterprise-grade
  - Minimalist
  - AI-enhanced

layout_philosophy:
  hero_style: "Architecture platform"
  dashboard_style: "Modern analytics"
  ai_style: "Subtle Bedrock-inspired purple accents"
  density: "Medium"
  whitespace: "Generous"
  shadows: "Minimal"

typography:
  display_xxl:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "64px"
    weight: 700

  display_xl:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "48px"
    weight: 700

  display_lg:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "32px"
    weight: 600

  heading:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "24px"
    weight: 600

  body:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "16px"
    weight: 400

  caption:
    family: "Inter Variable, Segoe UI, Arial, sans-serif"
    size: "13px"
    weight: 400

components:

  navbar:
    background: "#232F3E"
    text: "#FFFFFF"
    accent: "#FF9900"

  hero:
    background: "#232F3E"
    title_color: "#FFFFFF"
    subtitle_color: "#D5DBE3"
    accent_color: "#FF9900"

  metric_card:
    background: "#FFFFFF"
    border: "#D5DBE3"
    radius: "12px"

  upload_zone:
    background: "#FFFFFF"
    border: "2px dashed #FF9900"
    radius: "12px"

  chat_user:
    background: "#FFFFFF"
    border: "#D5DBE3"

  chat_assistant:
    background: "#EDE8FF"
    border: "#7B61FF"

  status_processing:
    color: "#7B61FF"

  status_completed:
    color: "#2E8540"

  status_failed:
    color: "#D13212"

dashboard:
  cards:
    invoices_processed:
      icon_color: "#FF9900"

    total_spend:
      icon_color: "#2E8540"

    ai_queries:
      icon_color: "#7B61FF"

pages:

  home:
    sections:
      - Hero
      - Upload
      - Invoice History
      - Conversational Analytics

  upload:
    features:
      - Drag and Drop PDF
      - Progress Bar
      - Status Tracking

  analytics:
    features:
      - Natural Language Query
      - SQL Generation
      - Athena Results
      - AI Summary

aws_branding:

  services:
    textract: "#FF9900"
    bedrock: "#7B61FF"
    athena: "#2E8540"
    s3: "#232F3E"
    step_functions: "#FF9900"

dos:
  - Use AWS Orange for primary actions
  - Use AWS Dark Blue for navigation and headers
  - Use Bedrock Purple only for AI features
  - Keep dashboards clean and architecture-oriented
  - Prioritize readability over visual effects

donts:
  - Do not use more than one AI accent color
  - Do not use neon colors
  - Do not overload screens with charts
  - Do not imitate AWS Console exactly
  - Do not use heavy shadows

success_definition:
  The interface should feel like a premium cloud-native analytics platform built on AWS, combining invoice processing, OCR, GenAI and conversational analytics into a single cohesive experience.
