# SPEC-010 - Static Web Portal for Invoice Upload

## Overview

Implement a serverless static web application that allows users to upload invoice documents and interact with the Invoice Analytics platform.

The web application will serve as the primary entry point for the Data Product and must be deployed entirely on AWS using serverless services.

---

## Business Goal

Enable non-technical users to:

* Upload invoice PDFs through a browser.
* Track processing status.
* Access invoice analytics through a conversational interface.

This eliminates the need for direct interaction with S3 buckets, CLI tools, or AWS consoles.

---

## Architecture


User Browser
      |
      v
CloudFront
      |
      v
S3 Static Website
      |
      +--------------------+
      |                    |
      v                    v

Upload API          Chat API

    |                    |

API Gateway      API Gateway

    |                    |

Lambda            Lambda

    |                    |

S3 Raw Bucket     Bedrock Query Layer

## Functional Requirements

### FR-001 - Invoice Upload

The system shall allow users to upload one or multiple PDF invoices.

Accepted formats:

* PDF

Maximum file size:

* 20 MB per file

---

### FR-002 - Upload Progress

The system shall display upload progress for each document.

Example:

invoice_001.pdf     Uploading... 75%
invoice_002.pdf     Completed
invoice_003.pdf     Failed


### FR-003 - Processing Status

The system shall display processing status for uploaded invoices.

Possible states:

* Uploaded
* Processing
* Completed
* Failed

---

### FR-004 - Invoice History

The system shall display previously processed invoices.

Suggested columns:

| Column       | Description         |
| ------------ | ------------------- |
| Invoice ID   | Internal identifier |
| Supplier     | Supplier name       |
| Invoice Date | Invoice date        |
| Total Amount | Extracted amount    |
| Status       | Processing status   |


## Non-Functional Requirements

### NFR-001

The solution shall be fully serverless.

---

### NFR-002

The frontend shall be deployable through Terraform.

---

### NFR-003

The frontend shall be statically hosted.

---

## AWS Services

* Amazon S3
* Amazon CloudFront
* Amazon API Gateway
* AWS Lambda
