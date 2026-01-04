# RadioOneAI – Backend

## Overview

The **RadioOneAI Backend** is the core service layer that powers AI-driven radiology workflows.  
It manages **clinical logic, AI orchestration, data persistence, role-based access, and communication** between the frontend and AI models.

The backend is designed with **clinical safety, scalability, and modularity** in mind, following a **human-in-the-loop** approach where AI assists clinicians but never replaces final medical decisions.

## Backend Responsibilities

- Secure authentication and role-based authorization  
- MRI scan ingestion and metadata management  
- AI pipeline orchestration (classification, detection, segmentation)  
- AI-assisted pre-report generation and versioning  
- Tumor severity estimation and urgency handling  
- Synthetic data management and quality metric tracking  
- Emergency alert triggering  
- REST API gateway for frontend and AI services  


## Core Backend Features

### Authentication & Authorization
- JWT-based authentication
- Role-based access control (RBAC)
  - Radiographer
  - Radiologist
  - Doctor
  - Admin
- Secure endpoint-level permission validation

### AI Pipeline Orchestration
The backend acts as a **controller layer** for multiple AI engines:
- Multi-level classification
- Tumor detection and verification
- Segmentation pipelines
- Synthetic data generation engines

All AI tasks are:
- Triggered through APIs
- Logged with metadata
- Versioned for traceability and auditing

### AI-Assisted Report Generation
- Stores AI-generated draft reports
- Supports radiologist review and editing
- Maintains report revision history
- Clearly separates **AI suggestions** from **final clinical approval**

---

### Data Management
- PostgreSQL relational database
- Manages:
  - Users and roles
  - Appointments
  - MRI scans and metadata
  - AI predictions
  - Reports and revisions
  - Synthetic datasets and evaluation metrics


### Synthetic Data Support
- Stores synthetic MRI metadata
- Tracks quality scores (SSIM, FID, PSNR)
- Enables dataset selection for model training
- Supports safe experimentation using anonymized data


## Tech Stack

- **Python**
- **Flask / FastAPI**
- **PostgreSQL**
- **SQLAlchemy**
- **JWT Authentication**
- **RESTful APIs**
- **Docker (optional)**
- **Postman**

---

## Backend Setup Guide

### Prerequisites
- Python **3.12**
- PostgreSQL
- pip
- virtualenv (recommended)

Check versions:
python --version
psql --version

git clone https://github.com/RadioOneAI/Backend.git

Go to command promt
*python -m venv venv
*venv\Scripts\activate
*pip install -r requirements.txt

## Database Setup

### Create the database: CREATE DATABASE radiooneai;
### Run migrations:
*python manage.py db init
*python manage.py db migrate
*python manage.py db upgrade

## Run the Backend Server : python run.py
## Backend runs at: http://localhost:5000
