/*
=====================================================================
REGISTRATION STEP 4 – DEPENDANTS
=====================================================================

Complete Step 4 JavaScript.

Parent status is captured once in Step 2.
This file never asks the user to select parent status again.
The selected Mother/Father determines which Step 2 status applies.

The server remains authoritative and validates/sanitises all submitted
values. This JavaScript only controls the user interface.
=====================================================================
*/

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const addButton = document.getElementById("addDepBtn");
        const container = document.getElementById("dependantsList");
        const indexesInput = document.getElementById("dependantIndexes");
        const cachedElement = document.getElementById("cachedDependants");
        const form = document.getElementById("registerStep4");

        if (!addButton || !container || !indexesInput || !form) {
            return;
        }

        const maritalStatus = String(
            form.dataset.maritalStatus || ""
        ).toUpperCase();

        const isMarried = maritalStatus === String(
            form.dataset.marriedValue || "MARRIED"
        ).toUpperCase();

        const parentStatuses = {
            MOTHER: String(form.dataset.motherStatus || "").toUpperCase(),
            FATHER: String(form.dataset.fatherStatus || "").toUpperCase()
        };

        let cachedDependants = [];
        let nextIndex = 1;

        if (cachedElement) {
            try {
                cachedDependants = JSON.parse(
                    cachedElement.textContent
                ) || [];
            } catch (error) {
                console.error(
                    "Unable to restore cached dependant data.",
                    error
                );
            }
        }

        function escapeHtml(value) {
            return String(value || "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/\"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function updateIndexes() {
            const indexes = [];

            container.querySelectorAll(
                ".dependant-item"
            ).forEach(function (card) {
                if (card.dataset.dependantIndex) {
                    indexes.push(card.dataset.dependantIndex);
                }
            });

            indexesInput.value = indexes.join(",");
        }

        function updateNumbers() {
            container.querySelectorAll(
                ".dependant-item"
            ).forEach(function (card, position) {
                const number = card.querySelector(
                    ".dependant-number"
                );

                if (number) {
                    number.textContent = "Dependant " + (position + 1);
                }
            });
        }

        function setIdentityState(card, required) {
            const first = card.querySelector(
                ".dependant-first-name"
            );
            const surname = card.querySelector(
                ".dependant-surname"
            );
            const dob = card.querySelector(
                ".dependant-dob"
            );

            [first, surname, dob].forEach(function (field) {
                if (field) {
                    field.required = required;
                }
            });
        }

        function clearIdentity(card) {
            const fields = [
                ".dependant-first-name",
                ".dependant-middle-name",
                ".dependant-surname",
                ".dependant-dob"
            ];

            fields.forEach(function (selector) {
                const field = card.querySelector(selector);
                if (field) {
                    field.value = "";
                }
            });
        }

        function clearLocation(card) {
            const fields = [
                ".dependant-country",
                ".dependant-county",
                ".dependant-sub-county-town"
            ];

            fields.forEach(function (selector) {
                const field = card.querySelector(selector);
                if (field) {
                    field.value = "";
                    field.required = false;
                }
            });
        }

        function setLocation(card, visible, required) {
            const wrapper = card.querySelector(
                ".dependant-location-fields"
            );

            const fields = [
                ".dependant-country",
                ".dependant-county",
                ".dependant-sub-county-town"
            ];

            if (wrapper) {
                wrapper.classList.toggle("d-none", !visible);
            }

            fields.forEach(function (selector) {
                const field = card.querySelector(selector);
                if (field) {
                    field.required = required;
                }
            });
        }

        function getParentStatus(card) {
            const parentType = card.querySelector(
                ".dependant-parent-type"
            );

            if (!parentType) {
                return "";
            }

            return parentStatuses[
                String(parentType.value || "").toUpperCase()
            ] || "";
        }

        function updateParentStatusDisplay(card) {
            const parentType = card.querySelector(
                ".dependant-parent-type"
            );
            const display = card.querySelector(
                ".dependant-parent-status-display"
            );

            if (!display) {
                return;
            }

            const type = String(
                parentType ? parentType.value : ""
            ).toUpperCase();

            const status = parentStatuses[type] || "";

            const labels = {
                ALIVE: "Alive",
                DECEASED: "Deceased",
                UNKNOWN: "Unknown"
            };

            if (!type) {
                display.textContent =
                    "Select Mother or Father to see the status captured in Step 2.";
                return;
            }

            display.textContent =
                labels[status] ||
                "Parent status is missing. Return to Step 2.";
        }

        function updateConditionalFields(card) {
            const relationship = card.querySelector(
                ".dependant-relationship"
            );
            const parentFields = card.querySelector(
                ".dependant-parent-fields"
            );
            const parentType = card.querySelector(
                ".dependant-parent-type"
            );

            if (!relationship || !parentFields) {
                return;
            }

            const relationshipValue = String(
                relationship.value || ""
            ).toUpperCase();

            parentFields.classList.add("d-none");

            if (parentType) {
                parentType.required = false;
            }

            setIdentityState(card, true);
            setLocation(card, false, false);

            if (relationshipValue === "CHILD") {
                clearLocation(card);
                return;
            }

            if (relationshipValue === "SPOUSE") {
                if (!isMarried) {
                    relationship.value = "";
                    clearLocation(card);
                    return;
                }

                setLocation(card, true, true);
                return;
            }

            if (relationshipValue === "SIBLING") {
                setLocation(card, true, true);
                return;
            }

            if (relationshipValue === "PARENT") {
                parentFields.classList.remove("d-none");

                if (parentType) {
                    parentType.required = true;
                }

                updateParentStatusDisplay(card);

                const status = getParentStatus(card);

                if (status === "UNKNOWN") {
                    clearIdentity(card);
                    clearLocation(card);
                    setIdentityState(card, false);
                    return;
                }

                if (status === "ALIVE") {
                    setIdentityState(card, true);
                    setLocation(card, true, true);
                    return;
                }

                if (status === "DECEASED") {
                    setIdentityState(card, true);
                    clearLocation(card);
                    setLocation(card, false, false);
                    return;
                }

                setIdentityState(card, true);
                clearLocation(card);
                return;
            }

            clearLocation(card);
        }

        function applyRelationshipLimits() {
            const relationshipSelects = container.querySelectorAll(
                ".dependant-relationship"
            );

            let spouseCount = 0;
            let parentCount = 0;

            relationshipSelects.forEach(function (select) {
                const value = String(
                    select.value || ""
                ).toUpperCase();

                if (value === "SPOUSE") {
                    spouseCount += 1;
                }

                if (value === "PARENT") {
                    parentCount += 1;
                }
            });

            relationshipSelects.forEach(function (select) {
                const spouse = select.querySelector(
                    'option[value="SPOUSE"]'
                );
                const parent = select.querySelector(
                    'option[value="PARENT"]'
                );

                if (spouse) {
                    spouse.disabled = (
                        !isMarried ||
                        (
                            spouseCount >= 1 &&
                            select.value !== "SPOUSE"
                        )
                    );
                }

                if (parent) {
                    parent.disabled = (
                        parentCount >= 2 &&
                        select.value !== "PARENT"
                    );
                }
            });
        }

        function bindCard(card) {
            const relationship = card.querySelector(
                ".dependant-relationship"
            );
            const parentType = card.querySelector(
                ".dependant-parent-type"
            );
            const removeButton = card.querySelector(
                ".remove-dep"
            );

            if (relationship) {
                relationship.addEventListener("change", function () {
                    updateConditionalFields(card);
                    applyRelationshipLimits();
                });
            }

            if (parentType) {
                parentType.addEventListener("change", function () {
                    updateParentStatusDisplay(card);
                    updateConditionalFields(card);
                });
            }

            if (removeButton) {
                removeButton.addEventListener("click", function () {
                    card.remove();
                    updateIndexes();
                    updateNumbers();
                    applyRelationshipLimits();
                });
            }

            updateConditionalFields(card);
        }

        function createCard(data, forcedIndex) {
            const index = forcedIndex || String(nextIndex++);
            const numericIndex = parseInt(index, 10);

            if (
                !Number.isNaN(numericIndex) &&
                numericIndex >= nextIndex
            ) {
                nextIndex = numericIndex + 1;
            }

            const card = document.createElement("div");
            card.className = "dependant-item dependant-card";
            card.dataset.dependantIndex = index;

            const relationship = String(
                data.relationship || ""
            ).toUpperCase();

            const parentType = String(
                data.parent_type || ""
            ).toUpperCase();

            card.innerHTML = `
                <div class="dependant-header">
                    <span class="dependant-number">Dependant</span>
                </div>

                <div class="row g-3">
                    <div class="col-12 col-md-4 dependant-name-field">
                        <label class="form-label">First Name</label>
                        <input
                            name="dep_${index}_first"
                            class="form-control dependant-first-name"
                            placeholder="Enter first name"
                            value="${escapeHtml(data.first_name || "")}"
                            required
                        >
                    </div>

                    <div class="col-12 col-md-4 dependant-name-field">
                        <label class="form-label">Middle Name</label>
                        <input
                            name="dep_${index}_middle"
                            class="form-control dependant-middle-name"
                            placeholder="Enter middle name"
                            value="${escapeHtml(data.middle_name || "")}"
                        >
                    </div>

                    <div class="col-12 col-md-4 dependant-name-field">
                        <label class="form-label">Surname</label>
                        <input
                            name="dep_${index}_surname"
                            class="form-control dependant-surname"
                            placeholder="Enter surname"
                            value="${escapeHtml(data.surname || "")}"
                            required
                        >
                    </div>
                </div>

                <div class="row g-3 mt-1">
                    <div class="col-12 col-md-6 dependant-dob-field">
                        <label class="form-label">Date of Birth</label>
                        <input
                            type="date"
                            name="dep_${index}_dob"
                            class="form-control dependant-dob"
                            value="${escapeHtml(data.dob || "")}"
                            required
                        >
                    </div>

                    <div class="col-12 col-md-6">
                        <label class="form-label">Relationship</label>
                        <select
                            name="dep_${index}_relation"
                            class="form-select dependant-relationship"
                            required
                        >
                            <option value="">Select relationship</option>
                            <option value="CHILD" ${relationship === "CHILD" ? "selected" : ""}>Child</option>
                            ${isMarried ? `<option value="SPOUSE" ${relationship === "SPOUSE" ? "selected" : ""}>Spouse</option>` : ""}
                            <option value="SIBLING" ${relationship === "SIBLING" ? "selected" : ""}>Sibling</option>
                            <option value="PARENT" ${relationship === "PARENT" ? "selected" : ""}>Parent</option>
                        </select>
                    </div>
                </div>

                <div class="row g-3 mt-1 dependant-parent-fields d-none">
                    <div class="col-12 col-md-6">
                        <label class="form-label">Parent Type</label>
                        <select
                            name="dep_${index}_parent_type"
                            class="form-select dependant-parent-type"
                        >
                            <option value="">Select parent type</option>
                            <option value="MOTHER" ${parentType === "MOTHER" ? "selected" : ""}>Mother</option>
                            <option value="FATHER" ${parentType === "FATHER" ? "selected" : ""}>Father</option>
                        </select>
                    </div>

                    <div class="col-12 col-md-6">
                        <label class="form-label">Parent Status</label>
                        <div
                            class="form-control bg-light dependant-parent-status-display"
                            aria-live="polite"
                        >
                            Select Mother or Father to see the status captured in Step 2.
                        </div>
                    </div>
                </div>

                <div class="row g-3 mt-1 dependant-location-fields d-none">
                    <div class="col-12 col-md-4">
                        <label class="form-label">Country</label>
                        <input
                            name="dep_${index}_country"
                            class="form-control dependant-country"
                            placeholder="Country"
                            value="${escapeHtml(data.country || "")}"
                        >
                    </div>

                    <div class="col-12 col-md-4">
                        <label class="form-label">County</label>
                        <input
                            name="dep_${index}_county"
                            class="form-control dependant-county"
                            placeholder="County"
                            value="${escapeHtml(data.county || "")}"
                        >
                    </div>

                    <div class="col-12 col-md-4">
                        <label class="form-label">Sub-county / Town</label>
                        <input
                            name="dep_${index}_sub_county_town"
                            class="form-control dependant-sub-county-town"
                            placeholder="Sub-county / Town"
                            value="${escapeHtml(data.sub_county_town || "")}"
                        >
                    </div>
                </div>

                <button
                    type="button"
                    class="btn btn-outline-danger btn-sm mt-3 remove-dep"
                >
                    Remove
                </button>
            `;

            container.appendChild(card);
            bindCard(card);
            updateIndexes();
            updateNumbers();
            applyRelationshipLimits();
        }

        addButton.addEventListener("click", function () {
            createCard({}, String(nextIndex++));
        });

        /*
         * Preserve the server-rendered first card when there is no cache.
         * When cached data exists, replace the blank first card with the
         * exact cached dependant collection.
         */
        const initialCards = Array.from(
            container.querySelectorAll(".dependant-item")
        );

        if (cachedDependants.length > 0) {
            initialCards.forEach(function (card) {
                card.remove();
            });

            cachedDependants.forEach(function (data) {
                createCard(
                    data,
                    String(nextIndex++)
                );
            });
        } else {
            initialCards.forEach(function (card) {
                bindCard(card);
            });
        }

        updateIndexes();
        updateNumbers();
        applyRelationshipLimits();
    });
})();
