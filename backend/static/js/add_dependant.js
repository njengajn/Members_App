(function () {

    "use strict";


    /* =====================================================
     * FORM
     * ===================================================== */

    const form =
        document.getElementById(
            "addDependantForm"
        );


    if (!form) {

        return;

    }


    /* =====================================================
     * RELATIONSHIP
     * ===================================================== */

    const relationshipSelect =
        document.getElementById(
            "id_relationship"
        );


    /* =====================================================
     * PARENT FIELDS
     * ===================================================== */

    const parentFields =
        document.getElementById(
            "parentFields"
        );

    const parentType =
        document.getElementById(
            "id_parent_type"
        );

    const parentStatus =
        document.getElementById(
            "id_parent_status"
        );


    /* =====================================================
     * LOCATION FIELDS
     * ===================================================== */

    const locationFields =
        document.getElementById(
            "locationFields"
        );

    const country =
        document.getElementById(
            "id_country"
        );

    const county =
        document.getElementById(
            "id_county"
        );

    const subCountyTown =
        document.getElementById(
            "id_sub_county_town"
        );


    /* =====================================================
     * PARENT LIMIT MESSAGE
     * ===================================================== */

    const parentTypeLimitMessage =
        document.getElementById(
            "parentTypeLimitMessage"
        );


    /* =====================================================
     * EXISTING COUNTS
     * ===================================================== */

    const existingSpouseCount =
        Number(
            form.dataset.existingSpouse || 0
        );


    const existingParentCount =
        Number(
            form.dataset.existingParents || 0
        );


    const existingMotherCount =
        Number(
            form.dataset.existingMothers || 0
        );


    const existingFatherCount =
        Number(
            form.dataset.existingFathers || 0
        );


    /* =====================================================
     * MARITAL STATUS
     * ===================================================== */

    const maritalStatus =
        String(
            form.dataset.maritalStatus || ""
        )
            .trim()
            .toUpperCase();


    const marriedValue =
        String(
            form.dataset.marriedValue || ""
        )
            .trim()
            .toUpperCase();


    const isMarried =
        maritalStatus !== ""
        && marriedValue !== ""
        && maritalStatus === marriedValue;


    /* =====================================================
     * LOCATION STATE
     * ===================================================== */

    function setLocationState(
        visible,
        required
    ) {

        if (locationFields) {

            if (visible) {

                locationFields.classList.remove(
                    "d-none"
                );

            } else {

                locationFields.classList.add(
                    "d-none"
                );

            }

        }


        if (country) {

            country.required =
                required;

        }


        if (county) {

            county.required =
                required;

        }


        if (subCountyTown) {

            subCountyTown.required =
                required;

        }

    }


    /* =====================================================
     * CLEAR LOCATION
     * ===================================================== */

    function clearLocationFields() {

        if (country) {

            country.value = "";

        }


        if (county) {

            county.value = "";

        }


        if (subCountyTown) {

            subCountyTown.value = "";

        }

    }


    /* =====================================================
     * UPDATE PARENT LOCATION
     * =====================================================
     *
     * Parent:
     *
     *     Alive
     *         -> location required
     *
     *     Deceased
     *         -> location not required
     *
     * Spouse and sibling:
     *
     *     -> location required
     *
     * Child:
     *
     *     -> no location
     * ===================================================== */

    function updateParentLocation() {

        if (
            !relationshipSelect
            || !parentStatus
        ) {

            return;

        }


        const relationship =
            String(
                relationshipSelect.value || ""
            )
                .trim()
                .toUpperCase();


        const status =
            String(
                parentStatus.value || ""
            )
                .trim()
                .toUpperCase();


        if (
            relationship === "PARENT"
            && status === "ALIVE"
        ) {

            setLocationState(
                true,
                true
            );

            return;

        }


        if (
            relationship === "PARENT"
            && status === "DECEASED"
        ) {

            setLocationState(
                false,
                false
            );

            return;

        }


        if (
            relationship === "SPOUSE"
            || relationship === "SIBLING"
        ) {

            setLocationState(
                true,
                true
            );

            return;

        }


        setLocationState(
            false,
            false
        );

    }


    /* =====================================================
     * UPDATE CONDITIONAL FIELDS
     * ===================================================== */

    function updateConditionalFields() {

        if (!relationshipSelect) {

            return;

        }


        const relationship =
            String(
                relationshipSelect.value || ""
            )
                .trim()
                .toUpperCase();


        /* =================================================
         * RESET
         * ================================================= */

        if (parentFields) {

            parentFields.classList.add(
                "d-none"
            );

        }


        if (parentType) {

            parentType.required =
                false;

        }


        if (parentStatus) {

            parentStatus.required =
                false;

        }


        setLocationState(
            false,
            false
        );


        /* =================================================
         * CHILD
         * ================================================= */

        if (
            relationship === "CHILD"
        ) {

            clearLocationFields();

            return;

        }


        /* =================================================
         * SPOUSE
         * ================================================= */

        if (
            relationship === "SPOUSE"
        ) {

            /*
             * A spouse is only valid for a married member.
             *
             * The backend also enforces this rule.
             */

            if (!isMarried) {

                relationshipSelect.value = "";

                clearLocationFields();

                return;

            }


            setLocationState(
                true,
                true
            );

            return;

        }


        /* =================================================
         * SIBLING
         * ================================================= */

        if (
            relationship === "SIBLING"
        ) {

            setLocationState(
                true,
                true
            );

            return;

        }


        /* =================================================
         * PARENT
         * ================================================= */

        if (
            relationship === "PARENT"
        ) {

            if (parentFields) {

                parentFields.classList.remove(
                    "d-none"
                );

            }


            if (parentType) {

                parentType.required =
                    true;

            }


            if (parentStatus) {

                parentStatus.required =
                    true;

            }


            updateParentLocation();

            return;

        }


        /* =================================================
         * EMPTY
         * ================================================= */

        clearLocationFields();

    }


    /* =====================================================
     * APPLY RELATIONSHIP LIMITS
     * ===================================================== */

    function applyRelationshipLimits() {

        if (!relationshipSelect) {

            return;

        }


        /* =================================================
         * SPOUSE
         * ================================================= */

        const spouseOption =
            relationshipSelect.querySelector(
                'option[value="SPOUSE"]'
            );


        if (spouseOption) {

            spouseOption.disabled =
                !isMarried
                || existingSpouseCount >= 1;

        }


        /* =================================================
         * PARENT
         * ================================================= */

        const parentOption =
            relationshipSelect.querySelector(
                'option[value="PARENT"]'
            );


        if (parentOption) {

            parentOption.disabled =
                existingParentCount >= 2;

        }

    }


    /* =====================================================
     * APPLY PARENT TYPE LIMITS
     * ===================================================== */

    function applyParentTypeLimits() {

        if (!parentType) {

            return;

        }


        const motherOption =
            parentType.querySelector(
                'option[value="MOTHER"]'
            );


        const fatherOption =
            parentType.querySelector(
                'option[value="FATHER"]'
            );


        if (motherOption) {

            motherOption.disabled =
                existingMotherCount >= 1;

        }


        if (fatherOption) {

            fatherOption.disabled =
                existingFatherCount >= 1;

        }


        /*
         * Do not display a permanent parent-limit message.
         *
         * The unavailable option itself communicates the
         * restriction.
         */

        if (parentTypeLimitMessage) {

            parentTypeLimitMessage.textContent =
                "";

            parentTypeLimitMessage.classList.add(
                "d-none"
            );

        }

    }


    /* =====================================================
     * RELATIONSHIP CHANGE
     * ===================================================== */

    if (relationshipSelect) {

        relationshipSelect.addEventListener(
            "change",
            function () {

                /*
                 * The disabled relationship options prevent
                 * normal selection of a relationship that has
                 * reached its limit.
                 */

                updateConditionalFields();

            }
        );

    }


    /* =====================================================
     * PARENT TYPE CHANGE
     * ===================================================== */

    if (parentType) {

        parentType.addEventListener(
            "change",
            function () {

                /*
                 * Keep browser behaviour predictable.
                 *
                 * Server-side validation remains authoritative.
                 */

                applyParentTypeLimits();

            }
        );

    }


    /* =====================================================
     * PARENT STATUS CHANGE
     * ===================================================== */

    if (parentStatus) {

        parentStatus.addEventListener(
            "change",
            function () {

                updateParentLocation();

            }
        );

    }


    /* =====================================================
     * INITIALISE
     * ===================================================== */

    applyRelationshipLimits();

    applyParentTypeLimits();

    updateConditionalFields();


    /* =====================================================
     * FINAL SUBMISSION CHECK
     * ===================================================== */

    form.addEventListener(
        "submit",
        function (event) {

            if (!relationshipSelect) {

                return;

            }


            const relationship =
                String(
                    relationshipSelect.value || ""
                )
                    .trim()
                    .toUpperCase();


            /* =============================================
             * SPOUSE
             * ============================================= */

            if (
                relationship === "SPOUSE"
                && (
                    !isMarried
                    || existingSpouseCount >= 1
                )
            ) {

                event.preventDefault();

                relationshipSelect.focus();

                return;

            }


            /* =============================================
             * PARENT
             * ============================================= */

            if (
                relationship === "PARENT"
                && existingParentCount >= 2
            ) {

                event.preventDefault();

                relationshipSelect.focus();

                return;

            }


            /* =============================================
             * MOTHER
             * ============================================= */

            if (
                relationship === "PARENT"
                && parentType
                && parentType.value === "MOTHER"
                && existingMotherCount >= 1
            ) {

                event.preventDefault();

                parentType.focus();

                return;

            }


            /* =============================================
             * FATHER
             * ============================================= */

            if (
                relationship === "PARENT"
                && parentType
                && parentType.value === "FATHER"
                && existingFatherCount >= 1
            ) {

                event.preventDefault();

                parentType.focus();

                return;

            }

        }
    );

})();