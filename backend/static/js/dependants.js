/*
=====================================================================
REGISTRATION STEP 4 – DEPENDANTS
=====================================================================

Parent eligibility is determined by the statuses captured in Step 2.
The statuses are deliberately not displayed on Step 4.

Only Mother/Father recorded as ALIVE are offered as parent choices.
If a parent is not eligible, their identity/location fields are never
shown or enabled.

The server must independently validate every submitted value.
=====================================================================
*/

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const form = document.getElementById("registerStep4");
        const addButton = document.getElementById("addDepBtn");
        const container = document.getElementById("dependantsList");
        const indexesInput = document.getElementById("dependantIndexes");
        const cachedElement = document.getElementById("cachedDependants");

        if (!form || !addButton || !container || !indexesInput) {
            return;
        }

        const maritalStatus = String(
            form.dataset.maritalStatus || ""
        ).trim().toUpperCase();

        const marriedValue = String(
            form.dataset.marriedValue || "MARRIED"
        ).trim().toUpperCase();

        const isMarried = maritalStatus === marriedValue;

        // Parent statuses are read silently from Step 2 data attributes.
        const parentStatuses = {
            MOTHER: String(form.dataset.motherStatus || "").trim().toUpperCase(),
            FATHER: String(form.dataset.fatherStatus || "").trim().toUpperCase()
        };

        function availableParentTypes() {
            return ["MOTHER", "FATHER"].filter(function (type) {
                return parentStatuses[type] === "ALIVE";
            });
        }

        function escapeHtml(value) {
            return String(value == null ? "" : value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function readCachedDependants() {
            if (!cachedElement) {
                return [];
            }

            try {
                const parsed = JSON.parse(cachedElement.textContent || "[]");
                return Array.isArray(parsed) ? parsed : [];
            } catch (error) {
                console.error("Unable to read saved dependant information.", error);
                return [];
            }
        }

        /*
         * Important restoration rule:
         * Do not filter a spouse merely because a status/field is missing
         * from the cached object. The registration session is the source
         * of the cached records. The server validates the marital rule.
         *
         * Only stale/ineligible parent entries are excluded because Step 4
         * must not create Deceased/Unknown parent dependant records.
         */
        function normaliseCachedDependants(items) {
            return items.filter(function (item) {
                if (!item || typeof item !== "object") {
                    return false;
                }

                const relationship = String(
                    item.relationship || item.relation || ""
                ).trim().toUpperCase();

                if (!["CHILD", "SPOUSE", "SIBLING", "PARENT"].includes(relationship)) {
                    return false;
                }

                if (relationship === "PARENT") {
                    const parentType = String(
                        item.parent_type || ""
                    ).trim().toUpperCase();

                    return availableParentTypes().includes(parentType);
                }

                // Preserve spouse/child/sibling entries exactly as cached.
                return true;
            }).map(function (item) {
                // Normalise legacy key spelling without losing any field values.
                return {
                    ...item,
                    relationship: String(
                        item.relationship || item.relation || ""
                    ).trim().toUpperCase()
                };
            });
        }

        let nextIndex = 1;

        function cards() {
            return Array.from(
                container.querySelectorAll(".dependant-item")
            );
        }

        function updateIndexes() {
            const indexes = cards().map(function (card) {
                return card.dataset.dependantIndex;
            }).filter(Boolean);

            indexesInput.value = indexes.join(",");
        }

        function updateNumbers() {
            cards().forEach(function (card, position) {
                const number = card.querySelector(".dependant-number");
                if (number) {
                    number.textContent = "Dependant " + (position + 1);
                }
            });
        }

        function setRequired(card, selectors, required) {
            selectors.forEach(function (selector) {
                const field = card.querySelector(selector);
                if (field) {
                    field.required = required;
                }
            });
        }

        function clearFields(card, selectors) {
            selectors.forEach(function (selector) {
                const field = card.querySelector(selector);
                if (field) {
                    field.value = "";
                }
            });
        }

        const identitySelectors = [
            ".dependant-first-name",
            ".dependant-surname",
            ".dependant-dob"
        ];

        const locationSelectors = [
            ".dependant-country",
            ".dependant-county",
            ".dependant-sub-county-town"
        ];

        function showLocation(card, visible, required) {
            const wrapper = card.querySelector(".dependant-location-fields");
            if (wrapper) {
                wrapper.classList.toggle("d-none", !visible);
            }
            setRequired(card, locationSelectors, required);
        }

        function parentFields(card) {
            return card.querySelector(".dependant-parent-fields");
        }

        function configureParentOptions(card) {
            const select = card.querySelector(".dependant-parent-type");
            if (!select) {
                return;
            }

            const allowed = availableParentTypes();
            const current = String(select.value || "").toUpperCase();

            // Keep only parent choices that Step 2 marked Alive.
            Array.from(select.options).forEach(function (option) {
                if (!option.value) {
                    return;
                }
                option.disabled = !allowed.includes(option.value.toUpperCase());
            });

            if (current && !allowed.includes(current)) {
                select.value = "";
            }

            // New cards are generated with only allowed options.
        }

        function updateCard(card) {
            const relationship = card.querySelector(".dependant-relationship");
            const parentWrapper = parentFields(card);
            const parentType = card.querySelector(".dependant-parent-type");

            if (!relationship || !parentWrapper) {
                return;
            }

            const relation = String(relationship.value || "").toUpperCase();

            // Default state: identity required, location and parent controls hidden.
            parentWrapper.classList.add("d-none");
            if (parentType) {
                parentType.required = false;
            }

            setRequired(card, identitySelectors, true);
            showLocation(card, false, false);

            if (relation === "CHILD") {
                clearFields(card, locationSelectors);
                return;
            }

            if (relation === "SPOUSE") {
                if (!isMarried) {
                    relationship.value = "";
                    clearFields(card, locationSelectors);
                    return;
                }

                showLocation(card, true, true);
                return;
            }

            if (relation === "SIBLING") {
                showLocation(card, true, true);
                return;
            }

            if (relation === "PARENT") {
                const allowed = availableParentTypes();

                if (!allowed.length) {
                    relationship.value = "";
                    parentWrapper.classList.add("d-none");
                    setRequired(card, identitySelectors, false);
                    clearFields(card, identitySelectors.concat(locationSelectors));
                    return;
                }

                parentWrapper.classList.remove("d-none");

                if (parentType) {
                    parentType.required = true;
                    configureParentOptions(card);
                }

                const selectedType = String(
                    parentType ? parentType.value : ""
                ).toUpperCase();

                // Never expose identity/location fields for an ineligible parent.
                if (!allowed.includes(selectedType)) {
                    setRequired(card, identitySelectors, false);
                    showLocation(card, false, false);
                    clearFields(card, identitySelectors.concat(locationSelectors));
                    return;
                }

                // An eligible Alive parent requires full identity and location.
                setRequired(card, identitySelectors, true);
                showLocation(card, true, true);
                return;
            }

            // No relationship selected.
            setRequired(card, identitySelectors, false);
            showLocation(card, false, false);
        }

        function selectedRelationshipCount(value) {
            return cards().filter(function (card) {
                const select = card.querySelector(".dependant-relationship");
                return select &&
                    String(select.value || "").toUpperCase() === value;
            }).length;
        }

        function applyLimits() {
            const spouseCount = selectedRelationshipCount("SPOUSE");
            const parentCount = selectedRelationshipCount("PARENT");

            cards().forEach(function (card) {
                const relationship = card.querySelector(".dependant-relationship");
                const parentType = card.querySelector(".dependant-parent-type");

                if (relationship) {
                    const spouseOption = relationship.querySelector('option[value="SPOUSE"]');
                    const parentOption = relationship.querySelector('option[value="PARENT"]');

                    if (spouseOption) {
                        spouseOption.disabled = (
                            !isMarried ||
                            (spouseCount >= 1 && relationship.value !== "SPOUSE")
                        );
                    }

                    if (parentOption) {
                        parentOption.disabled = (
                            availableParentTypes().length === 0 ||
                            (parentCount >= 2 && relationship.value !== "PARENT")
                        );
                    }
                }

                if (
                    !relationship ||
                    !parentType ||
                    String(relationship.value || "").toUpperCase() !== "PARENT"
                ) {
                    return;
                }

                const currentType = String(parentType.value || "").toUpperCase();

                Array.from(parentType.options).forEach(function (option) {
                    if (!option.value) {
                        return;
                    }

                    const type = option.value.toUpperCase();
                    const usedByAnotherCard = cards().some(function (otherCard) {
                        if (otherCard === card) {
                            return false;
                        }

                        const otherRelationship = otherCard.querySelector(
                            ".dependant-relationship"
                        );
                        const otherParentType = otherCard.querySelector(
                            ".dependant-parent-type"
                        );

                        return otherRelationship &&
                            otherParentType &&
                            String(otherRelationship.value || "").toUpperCase() === "PARENT" &&
                            String(otherParentType.value || "").toUpperCase() === type;
                    });

                    option.disabled = (
                        !availableParentTypes().includes(type) ||
                        (usedByAnotherCard && type !== currentType)
                    );
                });
            });
        }

        function bindCard(card) {
            const relationship = card.querySelector(".dependant-relationship");
            const parentType = card.querySelector(".dependant-parent-type");
            const removeButton = card.querySelector(".remove-dep");

            if (relationship) {
                relationship.addEventListener("change", function () {
                    updateCard(card);
                    applyLimits();
                });
            }

            if (parentType) {
                parentType.addEventListener("change", function () {
                    updateCard(card);
                    applyLimits();
                });
            }

            if (removeButton) {
                removeButton.addEventListener("click", function () {
                    card.remove();
                    updateIndexes();
                    updateNumbers();
                    applyLimits();
                });
            }

            updateCard(card);
        }

        function createCard(data, index) {
            const relationship = String(
                data.relationship || data.relation || ""
            ).toUpperCase();

            const parentType = String(
                data.parent_type || ""
            ).toUpperCase();

            const allowedParents = availableParentTypes();

            const parentOptions = allowedParents.map(function (type) {
                const label = type === "MOTHER" ? "Mother" : "Father";
                return `
                    <option value="${type}" ${parentType === type ? "selected" : ""}>
                        ${label}
                    </option>
                `;
            }).join("");

            const spouseOption = isMarried
                ? `<option value="SPOUSE" ${relationship === "SPOUSE" ? "selected" : ""}>Spouse</option>`
                : "";

            const parentRelationshipOption = allowedParents.length
                ? `<option value="PARENT" ${relationship === "PARENT" ? "selected" : ""}>Parent</option>`
                : "";

            const card = document.createElement("div");
            card.className = "dependant-item dependant-card";
            card.dataset.dependantIndex = String(index);

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
                            ${spouseOption}
                            <option value="SIBLING" ${relationship === "SIBLING" ? "selected" : ""}>Sibling</option>
                            ${parentRelationshipOption}
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
                            ${parentOptions}
                        </select>
                        <div class="form-text dependant-parent-warning d-none" role="alert">
                            Only a parent recorded as Alive can be added here.
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
        }

        // ---------------------------------------------------------
        // RESTORE OR CREATE CARDS
        // ---------------------------------------------------------

        const cached = normaliseCachedDependants(readCachedDependants());

        // Remove the static blank template card before restoring the
        // saved collection. This prevents it from being submitted as an
        // additional dependant alongside the restored records.
        cards().forEach(function (card) {
            card.remove();
        });

        if (cached.length) {
            /*
             * Use a deterministic index derived from the array position.
             * Do not increment a shared counter both outside and inside
             * createCard(). Each saved object maps to exactly one form card.
             */
            cached.forEach(function (item, position) {
                createCard(item, position + 1);
            });

            nextIndex = cached.length + 1;
        } else {
            // A clean registration starts with one blank dependant card.
            createCard({}, 1);
            nextIndex = 2;
        }

        function refreshFormState() {
            cards().forEach(updateCard);
            applyLimits();
            updateIndexes();
            updateNumbers();
        }

        refreshFormState();

        // Add a new card with a unique, sequential field index.
        addButton.addEventListener("click", function () {
            createCard({}, nextIndex);
            nextIndex += 1;
            refreshFormState();
        });

        // ---------------------------------------------------------
        // CLIENT-SIDE SUBMISSION GUARD
        // ---------------------------------------------------------

        form.addEventListener("submit", function (event) {
            const currentCards = cards();

            const spouseCount = selectedRelationshipCount("SPOUSE");
            const parentCards = currentCards.filter(function (card) {
                const relation = card.querySelector(".dependant-relationship");
                return relation &&
                    String(relation.value || "").toUpperCase() === "PARENT";
            });

            const selectedParents = parentCards.map(function (card) {
                const field = card.querySelector(".dependant-parent-type");
                return field ? String(field.value || "").toUpperCase() : "";
            });

            const duplicateParent = selectedParents.some(function (type, index) {
                return type && selectedParents.indexOf(type) !== index;
            });

            const invalidParent = selectedParents.some(function (type) {
                return !availableParentTypes().includes(type);
            });

            const invalidSpouse = (
                (!isMarried && spouseCount > 0) ||
                (isMarried && spouseCount > 1)
            );

            if (
                invalidSpouse ||
                parentCards.length > 2 ||
                duplicateParent ||
                invalidParent ||
                selectedParents.some(function (type) { return !type; })
            ) {
                event.preventDefault();

                window.alert(
                    "Please check the dependant details. A spouse can only be registered once when Married. Each Alive parent can only be registered once."
                );
                return;
            }

            // Always synchronise the indexes immediately before submit.
            updateIndexes();
        });
    });
})();