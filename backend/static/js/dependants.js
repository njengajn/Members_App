console.log("DEPENDANTS JS LOADED");


(function () {

    console.log("INIT RUNNING");


    /* =====================================================
     * PAGE ELEMENTS
     * ===================================================== */

    const addBtn =
        document.getElementById("addDepBtn");

    const container =
        document.getElementById("dependantsList");

    const indexesInput =
        document.getElementById("dependantIndexes");

    const cachedElement =
        document.getElementById("cachedDependants");


    if (
        !addBtn
        || !container
        || !indexesInput
    ) {

        console.log("❌ Elements not found");

        return;
    }


    /* =====================================================
     * CACHED DEPENDANTS
     * ===================================================== */

    let cachedDependants = [];


    if (cachedElement) {

        try {

            cachedDependants =
                JSON.parse(
                    cachedElement.textContent
                ) || [];

        } catch (error) {

            console.error(
                "Unable to load cached dependant data:",
                error
            );

        }
    }


    /* =====================================================
     * MEMBER MARITAL STATUS
     * =====================================================
     *
     * The template supplies:
     *
     *     data-marital-status
     *     data-married-value
     *
     * This is used for browser-side presentation only.
     *
     * The backend remains authoritative.
     * ===================================================== */

    const registerForm =
        document.getElementById("registerStep4");


    const maritalStatus =
        registerForm
            ? String(
                registerForm.getAttribute(
                    "data-marital-status"
                ) || ""
            )
                .trim()
                .toUpperCase()
            : "";


    const marriedValue =
        registerForm
            ? String(
                registerForm.getAttribute(
                    "data-married-value"
                ) || ""
            )
                .trim()
                .toUpperCase()
            : "";


    /*
     * IMPORTANT:
     *
     * There must be only ONE declaration of isMarried.
     * The previous version contained a duplicate declaration,
     * which caused a JavaScript syntax error.
     */

    const isMarried =
        maritalStatus !== ""
        && marriedValue !== ""
        && maritalStatus === marriedValue;


    /* =====================================================
     * NEXT UNIQUE INDEX
     * ===================================================== */

    let nextIndex = 1;


    /* =====================================================
     * ESCAPE HTML
     * ===================================================== */

    function escapeHtml(value) {

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");

    }


    /* =====================================================
     * UPDATE INDEX LIST
     * ===================================================== */

    function updateIndexes() {

        const indexes = [];


        container
            .querySelectorAll(
                ".dependant-item"
            )
            .forEach(function (item) {

                const index =
                    item.dataset.dependantIndex;


                if (index) {

                    indexes.push(index);

                }

            });


        indexesInput.value =
            indexes.join(",");

    }


    /* =====================================================
     * UPDATE VISIBLE NUMBERS
     * ===================================================== */

    function updateVisibleNumbers() {

        const items =
            container.querySelectorAll(
                ".dependant-item"
            );


        items.forEach(
            function (item, position) {

                const number =
                    item.querySelector(
                        ".dependant-number"
                    );


                if (number) {

                    number.textContent =
                        `Dependant ${position + 1}`;

                }

            }
        );

    }


    /* =====================================================
     * SET LOCATION STATE
     * ===================================================== */

    function setLocationState(
        card,
        visible,
        required
    ) {

        const locationFields =
            card.querySelector(
                ".dependant-location-fields"
            );

        const country =
            card.querySelector(
                ".dependant-country"
            );

        const county =
            card.querySelector(
                ".dependant-county"
            );

        const subCountyTown =
            card.querySelector(
                ".dependant-sub-county-town"
            );


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
     * CLEAR LOCATION FIELDS
     * ===================================================== */

    function clearLocationFields(card) {

        const country =
            card.querySelector(
                ".dependant-country"
            );

        const county =
            card.querySelector(
                ".dependant-county"
            );

        const subCountyTown =
            card.querySelector(
                ".dependant-sub-county-town"
            );


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
     *     ALIVE
     *         -> location shown and required
     *
     *     DECEASED
     *         -> location hidden and not required
     * ===================================================== */

    function updateParentLocationFields(card) {

        if (!card) {

            return;

        }


        const relationship =
            card.querySelector(
                ".dependant-relationship"
            );

        const parentStatus =
            card.querySelector(
                ".dependant-parent-status"
            );


        if (
            !relationship
            || !parentStatus
        ) {

            return;

        }


        const relationshipValue =
            String(
                relationship.value || ""
            ).toUpperCase();


        const statusValue =
            String(
                parentStatus.value || ""
            ).toUpperCase();


        if (
            relationshipValue === "PARENT"
            && statusValue === "ALIVE"
        ) {

            setLocationState(
                card,
                true,
                true
            );

        } else {

            setLocationState(
                card,
                false,
                false
            );

        }

    }


    /* =====================================================
     * UPDATE DEPENDANT CONDITIONAL FIELDS
     * ===================================================== */

    function updateDependantConditionalFields(card) {

        if (!card) {

            return;

        }


        const relationship =
            card.querySelector(
                ".dependant-relationship"
            );

        const parentFields =
            card.querySelector(
                ".dependant-parent-fields"
            );

        const parentType =
            card.querySelector(
                ".dependant-parent-type"
            );

        const parentStatus =
            card.querySelector(
                ".dependant-parent-status"
            );


        if (
            !relationship
            || !parentFields
        ) {

            return;

        }


        const relationshipValue =
            String(
                relationship.value || ""
            ).toUpperCase();


        /* =================================================
         * RESET
         * ================================================= */

        parentFields.classList.add(
            "d-none"
        );


        if (parentType) {

            parentType.required =
                false;

        }


        if (parentStatus) {

            parentStatus.required =
                false;

        }


        setLocationState(
            card,
            false,
            false
        );


        /* =================================================
         * CHILD
         * ================================================= */

        if (
            relationshipValue === "CHILD"
        ) {

            return;

        }


        /* =================================================
         * SPOUSE
         * ================================================= */

        if (
            relationshipValue === "SPOUSE"
        ) {

            /*
             * Spouse is only valid for a married member.
             *
             * The backend performs the authoritative check.
             */

            if (!isMarried) {

                relationship.value = "";

                clearLocationFields(card);

                return;

            }


            setLocationState(
                card,
                true,
                true
            );

            return;

        }


        /* =================================================
         * SIBLING
         * ================================================= */

        if (
            relationshipValue === "SIBLING"
        ) {

            setLocationState(
                card,
                true,
                true
            );

            return;

        }


        /* =================================================
         * PARENT
         * ================================================= */

        if (
            relationshipValue === "PARENT"
        ) {

            parentFields.classList.remove(
                "d-none"
            );


            if (parentType) {

                parentType.required =
                    true;

            }


            if (parentStatus) {

                parentStatus.required =
                    true;

            }


            updateParentLocationFields(
                card
            );

            return;

        }


        /* =================================================
         * EMPTY
         * ================================================= */

        clearLocationFields(card);

    }


    /* =====================================================
     * APPLY RELATIONSHIP LIMITS
     * ===================================================== */

    function applyRelationshipLimits() {

        const relationshipSelects =
            container.querySelectorAll(
                ".dependant-relationship"
            );


        let spouseCount = 0;

        let parentCount = 0;


        relationshipSelects.forEach(
            function (select) {

                const value =
                    String(
                        select.value || ""
                    )
                        .trim()
                        .toUpperCase();


                if (
                    value === "SPOUSE"
                ) {

                    spouseCount++;

                }


                if (
                    value === "PARENT"
                ) {

                    parentCount++;

                }

            }
        );


        relationshipSelects.forEach(
            function (select) {

                const spouseOption =
                    select.querySelector(
                        'option[value="SPOUSE"]'
                    );

                const parentOption =
                    select.querySelector(
                        'option[value="PARENT"]'
                    );


                /* -----------------------------------------
                 * SPOUSE
                 * ----------------------------------------- */

                if (spouseOption) {

                    spouseOption.disabled =
                        !isMarried
                        || (
                            spouseCount >= 1
                            && select.value !== "SPOUSE"
                        );

                }


                /* -----------------------------------------
                 * PARENT
                 * ----------------------------------------- */

                if (parentOption) {

                    parentOption.disabled =
                        parentCount >= 2
                        && select.value !== "PARENT";

                }

            }
        );

    }


    /* =====================================================
     * CREATE DEPENDANT
     * ===================================================== */

    function createDependant(
        data = null,
        forcedIndex = null
    ) {

        const index =
            forcedIndex !== null
                ? String(forcedIndex)
                : String(nextIndex++);


        const numericIndex =
            parseInt(index, 10);


        if (
            !Number.isNaN(numericIndex)
            && numericIndex >= nextIndex
        ) {

            nextIndex =
                numericIndex + 1;

        }


        const div =
            document.createElement("div");


        div.className =
            "dependant-item dependant-card";


        div.dataset.dependantIndex =
            index;


        div.style.opacity = "0";

        div.style.transform =
            "translateY(10px)";

        div.style.transition =
            "all 0.3s ease";


        const first =
            data?.first_name || "";

        const middle =
            data?.middle_name || "";

        const surname =
            data?.surname || "";

        const dob =
            data?.dob || "";

        const relationship =
            data?.relationship || "";

        const parentType =
            data?.parent_type || "";

        const parentStatus =
            data?.parent_status || "";

        const country =
            data?.country || "";

        const county =
            data?.county || "";

        const subCountyTown =
            data?.sub_county_town || "";


        /* =================================================
         * CREATE CARD HTML
         * ================================================= */

        div.innerHTML = `

            <div class="dependant-header">

                <span class="dependant-number">
                    Dependant
                </span>

            </div>


            <!-- ========================================= -->
            <!-- NAMES -->
            <!-- ========================================= -->

            <div class="row g-3">

                <div class="col-12 col-md-4">

                    <label class="form-label">
                        First Name
                    </label>

                    <input
                        name="dep_${index}_first"
                        class="form-control"
                        placeholder="Enter first name"
                        value="${escapeHtml(first)}"
                        required
                    >

                </div>


                <div class="col-12 col-md-4">

                    <label class="form-label">
                        Middle Name
                    </label>

                    <input
                        name="dep_${index}_middle"
                        class="form-control"
                        placeholder="Enter middle name"
                        value="${escapeHtml(middle)}"
                    >

                </div>


                <div class="col-12 col-md-4">

                    <label class="form-label">
                        Surname
                    </label>

                    <input
                        name="dep_${index}_surname"
                        class="form-control"
                        placeholder="Enter surname"
                        value="${escapeHtml(surname)}"
                        required
                    >

                </div>

            </div>


            <!-- ========================================= -->
            <!-- DOB + RELATIONSHIP -->
            <!-- ========================================= -->

            <div class="row g-3 mt-1">

                <div class="col-12 col-md-6">

                    <label class="form-label">
                        Date of Birth
                    </label>

                    <input
                        type="date"
                        name="dep_${index}_dob"
                        class="form-control"
                        value="${escapeHtml(dob)}"
                        required
                    >

                </div>


                <div class="col-12 col-md-6">

                    <label class="form-label">
                        Relationship
                    </label>

                    <select
                        name="dep_${index}_relation"
                        class="form-select dependant-relationship"
                        required
                    >

                        <option
                            value=""
                            ${!relationship ? "selected" : ""}
                        >
                            Select relationship
                        </option>


                        <option
                            value="CHILD"
                            ${relationship === "CHILD" ? "selected" : ""}
                        >
                            Child
                        </option>


                        ${
                            isMarried
                                ? `
                                    <option
                                        value="SPOUSE"
                                        ${relationship === "SPOUSE" ? "selected" : ""}
                                    >
                                        Spouse
                                    </option>
                                `
                                : ""
                        }


                        <option
                            value="SIBLING"
                            ${relationship === "SIBLING" ? "selected" : ""}
                        >
                            Sibling
                        </option>


                        <option
                            value="PARENT"
                            ${relationship === "PARENT" ? "selected" : ""}
                        >
                            Parent
                        </option>

                    </select>

                </div>

            </div>


            <!-- ========================================= -->
            <!-- PARENT TYPE / STATUS -->
            <!-- ========================================= -->

            <div
                class="row g-3 mt-1 dependant-parent-fields d-none"
            >

                <div class="col-12 col-md-6">

                    <label class="form-label">
                        Parent Type
                    </label>

                    <select
                        name="dep_${index}_parent_type"
                        class="form-select dependant-parent-type"
                    >

                        <option value="">
                            Select parent type
                        </option>

                        <option
                            value="MOTHER"
                            ${parentType === "MOTHER" ? "selected" : ""}
                        >
                            Mother
                        </option>

                        <option
                            value="FATHER"
                            ${parentType === "FATHER" ? "selected" : ""}
                        >
                            Father
                        </option>

                    </select>

                </div>


                <div class="col-12 col-md-6">

                    <label class="form-label">
                        Parent Status
                    </label>

                    <select
                        name="dep_${index}_parent_status"
                        class="form-select dependant-parent-status"
                    >

                        <option value="">
                            Select parent status
                        </option>

                        <option
                            value="ALIVE"
                            ${parentStatus === "ALIVE" ? "selected" : ""}
                        >
                            Alive
                        </option>

                        <option
                            value="DECEASED"
                            ${parentStatus === "DECEASED" ? "selected" : ""}
                        >
                            Deceased
                        </option>

                    </select>

                </div>

            </div>


            <!-- ========================================= -->
            <!-- LOCATION -->
            <!-- ========================================= -->

            <div
                class="row g-3 mt-1 dependant-location-fields d-none"
            >

                <div class="col-12 col-md-4">

                    <label class="form-label">
                        Country
                    </label>

                    <input
                        type="text"
                        name="dep_${index}_country"
                        class="form-control dependant-country"
                        placeholder="Enter country"
                        value="${escapeHtml(country)}"
                    >

                </div>


                <div class="col-12 col-md-4">

                    <label class="form-label">
                        County
                    </label>

                    <input
                        type="text"
                        name="dep_${index}_county"
                        class="form-control dependant-county"
                        placeholder="Enter county"
                        value="${escapeHtml(county)}"
                    >

                </div>


                <div class="col-12 col-md-4">

                    <label class="form-label">
                        Sub-county / Town
                    </label>

                    <input
                        type="text"
                        name="dep_${index}_sub_county_town"
                        class="form-control dependant-sub-county-town"
                        placeholder="Enter sub-county / town"
                        value="${escapeHtml(subCountyTown)}"
                    >

                </div>

            </div>


            <!-- ========================================= -->
            <!-- REMOVE -->
            <!-- ========================================= -->

            <button
                type="button"
                class="btn btn-sm btn-danger mt-3 remove-dep"
            >
                Remove
            </button>

        `;


        container.appendChild(div);


        /* =================================================
         * RELATIONSHIP CHANGE
         * ================================================= */

        const relationshipSelect =
            div.querySelector(
                ".dependant-relationship"
            );


        if (relationshipSelect) {

            relationshipSelect.addEventListener(
                "change",
                function () {

                    updateDependantConditionalFields(
                        div
                    );

                    applyRelationshipLimits();

                }
            );

        }


        /* =================================================
         * PARENT STATUS CHANGE
         * ================================================= */

        const parentStatusSelect =
            div.querySelector(
                ".dependant-parent-status"
            );


        if (parentStatusSelect) {

            parentStatusSelect.addEventListener(
                "change",
                function () {

                    updateParentLocationFields(
                        div
                    );

                }
            );

        }


        /* =================================================
         * INITIAL CONDITIONAL STATE
         * ================================================= */

        updateDependantConditionalFields(
            div
        );


        updateVisibleNumbers();

        updateIndexes();

        applyRelationshipLimits();


        /* =================================================
         * CARD ANIMATION
         * ================================================= */

        setTimeout(
            function () {

                div.style.opacity = "1";

                div.style.transform =
                    "translateY(0)";

            },
            10
        );

    }


    /* =====================================================
     * RESTORE CACHED DEPENDANTS
     * ===================================================== */

    if (
        cachedDependants.length > 0
    ) {

        container.innerHTML = "";

        nextIndex = 1;


        cachedDependants.forEach(
            function (data, position) {

                /*
                 * Cached registration data does not
                 * necessarily contain the original form
                 * index.
                 *
                 * Use sequential unique indexes when
                 * restoring the cached data.
                 */

                createDependant(
                    data,
                    position + 1
                );

            }
        );


    } else {

        /*
         * The original first dependant card is already
         * present in the template.
         */

        const firstItem =
            container.querySelector(
                ".dependant-item"
            );


        if (firstItem) {

            firstItem.dataset.dependantIndex =
                "1";


            nextIndex = 2;


            /* =========================================
             * INITIAL RELATIONSHIP HANDLER
             * ========================================= */

            const relationshipSelect =
                firstItem.querySelector(
                    ".dependant-relationship"
                );


            if (relationshipSelect) {

                relationshipSelect.addEventListener(
                    "change",
                    function () {

                        updateDependantConditionalFields(
                            firstItem
                        );

                        applyRelationshipLimits();

                    }
                );

            }


            /* =========================================
             * INITIAL PARENT STATUS HANDLER
             * ========================================= */

            const parentStatusSelect =
                firstItem.querySelector(
                    ".dependant-parent-status"
                );


            if (parentStatusSelect) {

                parentStatusSelect.addEventListener(
                    "change",
                    function () {

                        updateParentLocationFields(
                            firstItem
                        );

                    }
                );

            }


            /* =========================================
             * INITIAL CONDITIONAL STATE
             * ========================================= */

            updateDependantConditionalFields(
                firstItem
            );

        }


        updateIndexes();

        updateVisibleNumbers();

        applyRelationshipLimits();

    }


    /* =====================================================
     * ADD DEPENDANT
     * ===================================================== */

    addBtn.addEventListener(
        "click",
        function () {

            createDependant();

        }
    );


    /* =====================================================
     * REMOVE DEPENDANT
     * ===================================================== */

    container.addEventListener(
        "click",
        function (event) {

            if (
                !event.target.classList.contains(
                    "remove-dep"
                )
            ) {

                return;

            }


            const item =
                event.target.closest(
                    ".dependant-item"
                );


            if (!item) {

                return;

            }


            item.style.opacity = "0";

            item.style.transform =
                "translateY(-10px)";


            setTimeout(
                function () {

                    item.remove();

                    updateVisibleNumbers();

                    updateIndexes();

                    /*
                     * Removing a spouse or parent must
                     * immediately make that relationship
                     * available again.
                     */
                    applyRelationshipLimits();

                },
                300
            );

        }
    );


})();