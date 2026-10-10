/*
=====================================================================
REGISTRATION FIELD VALIDATION
=====================================================================

This file provides frontend assistance only.
Django server-side validation remains authoritative.

Phone rules:
    - UK local mobile: exactly 11 characters, beginning 07.
    - UK international mobile: exactly 13 characters, +447XXXXXXXXX.
    - Only digits are permitted, except for the leading + in +44.

Email rules:
    - Browser email validation is supplemented with a simple format
      check before submission.
=====================================================================
*/

(function () {
    "use strict";

    const PHONE_SELECTOR = 'input[name="phone"]';
    const EMAIL_SELECTOR = 'input[type="email"][name="email"]';
    const USERNAME_SELECTOR = 'input[name="username"]';

    function validateUsernameField(field) {
        const value = field.value;

        if (!value) {
            setInvalid(field, "Please enter a username.");
            return false;
        }

        if (!/^[A-Za-z0-9._-]{1,21}$/.test(value)) {
            setInvalid(
                field,
                "Username must be 1–21 characters and may contain only letters, digits, dot (.), underscore (_) or hyphen (-). No spaces or other special characters are allowed."
            );
            return false;
        }

        clearInvalid(field);
        return true;
    }

    function initialiseUsername(field) {
        field.setAttribute("maxlength", "21");
        field.setAttribute("autocomplete", "username");

        field.addEventListener("input", function () {
            // Do not silently alter the value: invalid input should be
            // visible to the user and rejected consistently by Django.
            validateUsernameField(field);
        });

        field.addEventListener("blur", function () {
            validateUsernameField(field);
        });
    }

    function normalisePhoneInput(value) {
        let cleaned = String(value || "").replace(/[^0-9+]/g, "");

        if (cleaned.indexOf("+") > 0) {
            cleaned = cleaned.replace(/\+/g, "");
        }

        if (cleaned.startsWith("+")) {
            cleaned = "+" + cleaned.slice(1).replace(/\+/g, "");
            return cleaned.slice(0, 13);
        }

        return cleaned.replace(/\+/g, "").slice(0, 11);
    }

    function isValidUkMobile(value) {
        return /^07\d{9}$/.test(value) || /^\+447\d{9}$/.test(value);
    }

    function isValidEmail(value) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    }

    function setInvalid(field, message) {
        field.setCustomValidity(message);
        field.classList.add("is-invalid");
    }

    function clearInvalid(field) {
        field.setCustomValidity("");
        field.classList.remove("is-invalid");
    }

    function validatePhoneField(field) {
        const value = field.value.trim();

        if (!value) {
            setInvalid(field, "Please enter a UK mobile phone number.");
            return false;
        }

        if (!isValidUkMobile(value)) {
            setInvalid(
                field,
                "Enter exactly 11 digits beginning 07, or the 13-character +44 format."
            );
            return false;
        }

        clearInvalid(field);
        return true;
    }

    function validateEmailField(field) {
        const value = field.value.trim();

        if (!value) {
            setInvalid(field, "Please enter an email address.");
            return false;
        }

        if (!isValidEmail(value)) {
            setInvalid(field, "Please enter a valid email address.");
            return false;
        }

        clearInvalid(field);
        return true;
    }

    function initialisePhone(field) {
        field.setAttribute("maxlength", "13");
        field.setAttribute("inputmode", "tel");
        field.setAttribute("autocomplete", "tel");

        field.addEventListener("input", function () {
            field.value = normalisePhoneInput(field.value);
            clearInvalid(field);
        });

        field.addEventListener("blur", function () {
            validatePhoneField(field);
        });
    }

    function initialiseEmail(field) {
        field.setAttribute("autocomplete", "email");

        field.addEventListener("input", function () {
            clearInvalid(field);
        });

        field.addEventListener("blur", function () {
            validateEmailField(field);
        });
    }

    function initialise() {
        document.querySelectorAll(PHONE_SELECTOR).forEach(initialisePhone);
        document.querySelectorAll(EMAIL_SELECTOR).forEach(initialiseEmail);
        document.querySelectorAll(USERNAME_SELECTOR).forEach(initialiseUsername);

        const forms = document.querySelectorAll("form");

        forms.forEach(function (form) {
            form.addEventListener("submit", function (event) {
                let valid = true;

                form.querySelectorAll(USERNAME_SELECTOR).forEach(function (field) {
                    if (!validateUsernameField(field)) {
                        valid = false;
                    }
                });

                form.querySelectorAll(PHONE_SELECTOR).forEach(function (field) {
                    if (!validatePhoneField(field)) {
                        valid = false;
                    }
                });

                form.querySelectorAll(EMAIL_SELECTOR).forEach(function (field) {
                    if (!validateEmailField(field)) {
                        valid = false;
                    }
                });

                if (!valid) {
                    event.preventDefault();
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", initialise);
})();
