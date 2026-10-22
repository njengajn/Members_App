import random
from django.utils import timezone
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail

from backend.members.models import EmailOTP

User = get_user_model()
