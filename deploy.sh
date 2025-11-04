#!/bin/bash

# Quick deployment script for Jalin App
# Frontend: https://github.com/Ayash13/Jalin-App-v2.git
# Backend: https://github.com/Ayash13/JalinApp-REN.git

python3 deploy_agent.py \
    --fe-repo https://github.com/Ayash13/Jalin-App-v2.git \
    --be-repo https://github.com/Ayash13/JalinApp-REN.git

