console.log("DEPENDANTS JS LOADED");


(function () {

    console.log("INIT RUNNING");

    const addBtn =
        document.getElementById("addDepBtn");

    const container =
        document.getElementById("dependantsList");

    const indexesInput =
        document.getElementById("dependantIndexes");

    const cachedElement =
        document.getElementById("cachedDependants");


    if (!addBtn || !container || !indexesInput) {

        console.log("❌ Elements not found");

        return;
    }


    /*
     * =====================================================
     * CACHED DEPENDANTS
     * =====================================================
     */

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


    /*
     * =====================================================
     * NEXT UNIQUE INDEX
     * =====================================================
     *
     * This number is NOT the visible dependant number.
     *
     * It is a unique identifier for the form fields.
     */

    let nextIndex = 1;


    /*
     * =====================================================
     * ESCAPE HTML
     * =====================================================
     */

    function escapeHtml(value) {

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }


    /*
     * =====================================================
     * UPDATE INDEX LIST
     * =====================================================
     */

    function updateIndexes() {

        const indexes = [];

        container
            .querySelectorAll(".dependant-item")
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


    /*
     * =====================================================
     * UPDATE VISIBLE NUMBERS
     * =====================================================
     *
     * The database/form index remains unchanged.
     *
     * Only the displayed number changes.
     */

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


    /*
     * =====================================================
     * CREATE DEPENDANT
     * =====================================================
     */

    function createDependant(data = null, forcedIndex = null) {

        const index =
            forcedIndex !== null
                ? String(forcedIndex)
                : String(nextIndex++);


        /*
         * Keep nextIndex ahead of restored indexes.
         */

        const numericIndex =
            parseInt(index, 10);

        if (
            !Number.isNaN(numericIndex) &&
            numericIndex >= nextIndex
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
            data?.relationship || "CHILD";


        div.innerHTML = `

            <div class="dependant-header">

                <span class="dependant-number">
                    Dependant
                </span>

            </div>


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
                        class="form-select"
                        required
                    >

                        <option
                            value="CHILD"
                            ${relationship === "CHILD" ? "selected" : ""}
                        >
                            Child
                        </option>

                        <option
                            value="SPOUSE"
                            ${relationship === "SPOUSE" ? "selected" : ""}
                        >
                            Spouse
                        </option>

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

                        <option
                            value="OTHER"
                            ${relationship === "OTHER" ? "selected" : ""}
                        >
                            Other
                        </option>

                    </select>

                </div>

            </div>


            <button
                type="button"
                class="btn btn-sm btn-danger mt-3 remove-dep"
            >
                Remove
            </button>

        `;


        container.appendChild(div);


        updateVisibleNumbers();

        updateIndexes();


        setTimeout(function () {

            div.style.opacity = "1";

            div.style.transform =
                "translateY(0)";

        }, 10);

    }


    /*
     * =====================================================
     * RESTORE CACHED DEPENDANTS
     * =====================================================
     */

    if (cachedDependants.length > 0) {

        container.innerHTML = "";

        nextIndex = 1;


        cachedDependants.forEach(
            function (data) {

                createDependant(data);

            }
        );

    } else {

        /*
         * The original first dependant card is already
         * present in the template.
         *
         * Give it a unique index.
         */

        const firstItem =
            container.querySelector(
                ".dependant-item"
            );

        if (firstItem) {

            firstItem.dataset.dependantIndex =
                "1";

            nextIndex = 2;

        }

        updateIndexes();

        updateVisibleNumbers();

    }


    /*
     * =====================================================
     * ADD DEPENDANT
     * =====================================================
     */

    addBtn.addEventListener(
        "click",
        function () {

            createDependant();

        }
    );


    /*
     * =====================================================
     * REMOVE DEPENDANT
     * =====================================================
     */

    container.addEventListener(
        "click",
        function (e) {

            if (
                !e.target.classList.contains(
                    "remove-dep"
                )
            ) {

                return;
            }


            const item =
                e.target.closest(
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

                },
                300
            );

        }
    );


})();