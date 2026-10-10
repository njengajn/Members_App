(function () {
    "use strict";

    const form = document.getElementById("addDependantForm");
    if (!form) return;

    const relationshipSelect = document.getElementById("id_relationship");
    const parentFields = document.getElementById("parentFields");
    const parentType = document.getElementById("id_parent_type");
    const parentStatus = document.getElementById("id_parent_status");
    const locationFields = document.getElementById("locationFields");
    const country = document.getElementById("id_country");
    const county = document.getElementById("id_county");
    const subCountyTown = document.getElementById("id_sub_county_town");

    const existingSpouseCount = Number(form.dataset.existingSpouse || 0);
    const existingParentCount = Number(form.dataset.existingParents || 0);
    const existingMotherCount = Number(form.dataset.existingMothers || 0);
    const existingFatherCount = Number(form.dataset.existingFathers || 0);

    const maritalStatus = String(form.dataset.maritalStatus || "").trim().toUpperCase();
    const marriedValue = String(form.dataset.marriedValue || "").trim().toUpperCase();
    const isMarried = maritalStatus !== "" && marriedValue !== "" && maritalStatus === marriedValue;

    function setLocationState(visible, required) {
        if (locationFields) {
            locationFields.classList.toggle("d-none", !visible);
        }
        [country, county, subCountyTown].forEach(function (field) {
            if (field) field.required = required;
        });
    }

    function clearLocationFields() {
        [country, county, subCountyTown].forEach(function (field) {
            if (field) field.value = "";
        });
    }

    function updateParentLocation() {
        if (!relationshipSelect || !parentStatus) return;

        const relationship = String(relationshipSelect.value || "").trim().toUpperCase();
        const status = String(parentStatus.value || "").trim().toUpperCase();

        if (relationship === "PARENT" && status === "ALIVE") {
            setLocationState(true, true);
        } else if (
            relationship === "PARENT" &&
            (status === "DECEASED" || status === "UNKNOWN")
        ) {
            setLocationState(false, false);
            clearLocationFields();
        } else if (relationship === "SPOUSE" || relationship === "SIBLING") {
            setLocationState(true, true);
        } else {
            setLocationState(false, false);
            clearLocationFields();
        }
    }

    function updateConditionalFields() {
        if (!relationshipSelect) return;

        const relationship = String(relationshipSelect.value || "").trim().toUpperCase();

        if (parentFields) parentFields.classList.add("d-none");
        if (parentType) parentType.required = false;
        if (parentStatus) parentStatus.required = false;
        setLocationState(false, false);

        if (relationship === "CHILD") {
            clearLocationFields();
            return;
        }

        if (relationship === "SPOUSE") {
            if (!isMarried) {
                relationshipSelect.value = "";
                clearLocationFields();
                return;
            }
            setLocationState(true, true);
            return;
        }

        if (relationship === "SIBLING") {
            setLocationState(true, true);
            return;
        }

        if (relationship === "PARENT") {
            if (parentFields) parentFields.classList.remove("d-none");
            if (parentType) parentType.required = true;
            if (parentStatus) parentStatus.required = true;
            updateParentLocation();
            return;
        }

        clearLocationFields();
    }

    function applyRelationshipLimits() {
        if (!relationshipSelect) return;

        const spouseOption = relationshipSelect.querySelector('option[value="SPOUSE"]');
        if (spouseOption) {
            spouseOption.disabled = !isMarried || existingSpouseCount >= 1;
        }

        const parentOption = relationshipSelect.querySelector('option[value="PARENT"]');
        if (parentOption) {
            parentOption.disabled = existingParentCount >= 2;
        }
    }

    function applyParentTypeLimits() {
        if (!parentType) return;

        const motherOption = parentType.querySelector('option[value="MOTHER"]');
        const fatherOption = parentType.querySelector('option[value="FATHER"]');

        if (motherOption) motherOption.disabled = existingMotherCount >= 1;
        if (fatherOption) fatherOption.disabled = existingFatherCount >= 1;
    }

    if (relationshipSelect) {
        relationshipSelect.addEventListener("change", updateConditionalFields);
    }

    if (parentType) {
        parentType.addEventListener("change", applyParentTypeLimits);
    }

    if (parentStatus) {
        parentStatus.addEventListener("change", updateParentLocation);
    }

    applyRelationshipLimits();
    applyParentTypeLimits();
    updateConditionalFields();

    form.addEventListener("submit", function (event) {
        const relationship = String(relationshipSelect?.value || "").trim().toUpperCase();

        if (relationship === "SPOUSE" && (!isMarried || existingSpouseCount >= 1)) {
            event.preventDefault();
            relationshipSelect?.focus();
            return;
        }

        if (relationship === "PARENT" && existingParentCount >= 2) {
            event.preventDefault();
            relationshipSelect?.focus();
            return;
        }

        if (relationship === "PARENT" && parentType?.value === "MOTHER" && existingMotherCount >= 1) {
            event.preventDefault();
            parentType.focus();
            return;
        }

        if (relationship === "PARENT" && parentType?.value === "FATHER" && existingFatherCount >= 1) {
            event.preventDefault();
            parentType.focus();
        }
    });
})();
