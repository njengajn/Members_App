// ============================================================
// CLAIM SEARCH / CLAIM CREATION JAVASCRIPT
// ============================================================
//
// IMPORTANT
// ------------------------------------------------------------
// This is the ONLY claim-creation JavaScript loaded by:
//
// admin_create_claim.html
//
// It controls:
// - Claim type switching
// - Member search
// - Member selection
// - Affected person
// - Next of kin display
// - Multiple document selection
// - Document previews
// - Bank input formatting/validation
//
// DO NOT load claim_form.js alongside this file.
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        console.log(
            "Claim JS loaded ✅"
        );

        // ====================================================
        // CLAIM ELEMENTS
        // ====================================================

        const causeType =
            document.getElementById(
                "id_cause_type"
            );

        const dependantSelect =
            document.getElementById(
                "id_causer_dependant"
            );

        const searchWrapper =
            document.getElementById(
                "member-search-wrapper"
            );

        const dependantWrapper =
            document.getElementById(
                "dependant-wrapper"
            );

        const searchInput =
            document.getElementById(
                "member-search"
            );

        const results =
            document.getElementById(
                "search-results"
            );

        const hiddenInput =
            document.getElementById(
                "selected_member_id"
            );

        const affected =
            document.getElementById(
                "affected-person"
            );

        const nextOfKinSection =
            document.getElementById(
                "next-of-kin-section"
            );

        const nextOfKinName =
            document.getElementById(
                "next-of-kin-name"
            );

        const nextOfKinRelationship =
            document.getElementById(
                "next-of-kin-relationship"
            );

        const nextOfKinPhone =
            document.getElementById(
                "next-of-kin-phone"
            );

        const nextOfKinEmail =
            document.getElementById(
                "next-of-kin-email"
            );

        // ====================================================
        // FILE ELEMENTS
        // ====================================================

        const fileInput =
            document.getElementById(
                "file-input"
            );

        const fileList =
            document.getElementById(
                "file-list"
            );

        const dropZone =
            document.getElementById(
                "drop-zone"
            );

        // ====================================================
        // BANK ELEMENTS
        // ====================================================

        const sortCode =
            document.getElementById(
                "id_sort_code"
            );

        const accountNumber =
            document.getElementById(
                "id_account_number"
            );

        const accountOpenedDate =
            document.getElementById(
                "id_account_opened_date"
            );

        // ====================================================
        // CLAIM TYPE TOGGLE
        // ====================================================

        function toggleUI() {

            if (!causeType) {
                return;
            }

            if (
                causeType.value
                === "member"
            ) {

                if (searchWrapper) {
                    searchWrapper.style.display =
                        "block";
                }

                if (dependantWrapper) {
                    dependantWrapper.style.display =
                        "none";
                }

            } else {

                if (searchWrapper) {
                    searchWrapper.style.display =
                        "none";
                }

                if (dependantWrapper) {
                    dependantWrapper.style.display =
                        "block";
                }

                if (hiddenInput) {
                    hiddenInput.value = "";
                }

                clearNextOfKin();
            }
        }

        if (causeType) {

            causeType.addEventListener(
                "change",
                toggleUI
            );

            toggleUI();
        }

        // ====================================================
        // DEPENDANT → AFFECTED PERSON
        // ====================================================

        if (dependantSelect) {

            dependantSelect.addEventListener(
                "change",
                function () {

                    if (!affected) {
                        return;
                    }

                    if (
                        this.selectedIndex
                        >= 0
                    ) {

                        affected.value =
                            this.options[
                                this.selectedIndex
                            ].text;
                    }
                }
            );
        }

        // ====================================================
        // CLEAR NEXT OF KIN
        // ====================================================

        function clearNextOfKin() {

            if (nextOfKinSection) {

                nextOfKinSection.style.display =
                    "none";
            }

            if (nextOfKinName) {
                nextOfKinName.textContent =
                    "";
            }

            if (nextOfKinRelationship) {
                nextOfKinRelationship.textContent =
                    "";
            }

            if (nextOfKinPhone) {
                nextOfKinPhone.textContent =
                    "";
            }

            if (nextOfKinEmail) {
                nextOfKinEmail.textContent =
                    "";
            }
        }

        // ====================================================
        // DISPLAY NEXT OF KIN
        // ====================================================

        function displayNextOfKin(
            nok
        ) {

            if (
                !nok
                || !nok.name
            ) {

                clearNextOfKin();

                return;
            }

            if (nextOfKinSection) {

                nextOfKinSection.style.display =
                    "block";
            }

            if (nextOfKinName) {

                nextOfKinName.textContent =
                    nok.name;
            }

            if (nextOfKinRelationship) {

                nextOfKinRelationship.textContent =
                    nok.relationship
                    || "Not specified";
            }

            if (nextOfKinPhone) {

                nextOfKinPhone.textContent =
                    nok.phone
                    || "Not specified";
            }

            if (nextOfKinEmail) {

                nextOfKinEmail.textContent =
                    nok.email
                    || "Not specified";
            }
        }

        // ====================================================
        // MEMBER SEARCH
        // ====================================================

        if (searchInput) {

            searchInput.addEventListener(
                "keyup",
                function () {

                    const query =
                        this.value.trim();

                    if (query.length < 2) {

                        if (results) {
                            results.innerHTML =
                                "";
                        }

                        return;
                    }

                    fetch(
                        `/admin-panel/claims/search-members/?q=${encodeURIComponent(query)}`
                    )
                    .then(
                        response => {

                            if (
                                !response.ok
                            ) {

                                throw new Error(
                                    "Member search failed."
                                );
                            }

                            return response.json();
                        }
                    )
                    .then(
                        data => {

                            if (!results) {
                                return;
                            }

                            results.innerHTML =
                                "";

                            data.forEach(
                                member => {

                                    const item =
                                        document.createElement(
                                            "a"
                                        );

                                    item.classList.add(
                                        "list-group-item",
                                        "list-group-item-action"
                                    );

                                    item.style.cursor =
                                        "pointer";

                                    const uid =
                                        member.uid
                                        || "N/A";

                                    const email =
                                        member.email
                                        || "No email";

                                    item.innerHTML =
                                        `
                                        <strong>
                                            ${escapeHtml(member.name)}
                                        </strong>
                                        <br>
                                        <small>
                                            UID:
                                            ${escapeHtml(uid)}
                                            &nbsp; | &nbsp;
                                            ${escapeHtml(email)}
                                        </small>
                                        `;

                                    item.addEventListener(
                                        "click",
                                        function () {

                                            // --------------------------------
                                            // Preserve working selection.
                                            // --------------------------------

                                            hiddenInput.value =
                                                member.id;

                                            affected.value =
                                                `${member.name} (UID: ${uid})`;

                                            results.innerHTML =
                                                "";

                                            searchInput.value =
                                                member.name;

                                            // --------------------------------
                                            // NEW:
                                            // Display next of kin.
                                            // --------------------------------

                                            displayNextOfKin(
                                                member.next_of_kin
                                            );
                                        }
                                    );

                                    results.appendChild(
                                        item
                                    );
                                }
                            );
                        }
                    )
                    .catch(
                        error => {

                            console.error(
                                "Member search error:",
                                error
                            );
                        }
                    );
                }
            );
        }

        // ====================================================
        // SIMPLE HTML ESCAPING
        // ====================================================

        function escapeHtml(
            value
        ) {

            const div =
                document.createElement(
                    "div"
                );

            div.textContent =
                value == null
                    ? ""
                    : String(value);

            return div.innerHTML;
        }

        // ====================================================
        // FILE PREVIEW
        // ====================================================

        function createPreview(
            file
        ) {

            if (!fileList) {
                return;
            }

            const container =
                document.createElement(
                    "div"
                );

            container.classList.add(
                "border",
                "p-2",
                "mb-2"
            );

            let preview =
                "";

            if (
                file.type.startsWith(
                    "image"
                )
            ) {

                preview =
                    `
                    <img
                        src="${URL.createObjectURL(file)}"
                        width="100"
                        class="mb-2"
                        alt="Document preview"
                    />
                    `;
            }

            const progressId =
                "progress_"
                + Math.random()
                    .toString(36)
                    .substr(2, 9);

            container.innerHTML =
                `
                ${preview}

                <strong>
                    ${escapeHtml(file.name)}
                </strong>

                <input
                    type="text"
                    name="doc_title"
                    placeholder="Title"
                    class="form-control mt-2"
                >

                <textarea
                    name="doc_description"
                    placeholder="Description"
                    class="form-control mt-2"
                ></textarea>

                <div class="progress mt-2">

                    <div
                        id="${progressId}"
                        class="progress-bar"
                        role="progressbar"
                        style="width: 0%"
                    >
                        0%
                    </div>

                </div>
                `;

            fileList.appendChild(
                container
            );

            simulateProgress(
                progressId
            );
        }

        // ====================================================
        // SIMULATED PROGRESS
        // ====================================================

        function simulateProgress(
            id
        ) {

            let progress = 0;

            const bar =
                document.getElementById(
                    id
                );

            const interval =
                setInterval(
                    function () {

                        progress += 10;

                        if (bar) {

                            bar.style.width =
                                progress
                                + "%";

                            bar.innerText =
                                progress
                                + "%";
                        }

                        if (
                            progress
                            >= 100
                        ) {

                            clearInterval(
                                interval
                            );
                        }

                    },
                    100
                );
        }

        // ====================================================
        // HANDLE FILES
        // ====================================================

        function handleFiles(
            files
        ) {

            Array.from(
                files
            ).forEach(
                function (file) {

                    createPreview(
                        file
                    );
                }
            );
        }

        if (fileInput) {

            fileInput.addEventListener(
                "change",
                function () {

                    handleFiles(
                        this.files
                    );
                }
            );
        }

        // ====================================================
        // DRAG AND DROP
        // ====================================================

        if (dropZone) {

            dropZone.addEventListener(
                "dragover",
                function (event) {

                    event.preventDefault();

                    dropZone.classList.add(
                        "bg-light"
                    );
                }
            );

            dropZone.addEventListener(
                "dragleave",
                function () {

                    dropZone.classList.remove(
                        "bg-light"
                    );
                }
            );

            dropZone.addEventListener(
                "drop",
                function (event) {

                    event.preventDefault();

                    dropZone.classList.remove(
                        "bg-light"
                    );

                    handleFiles(
                        event.dataTransfer.files
                    );
                }
            );
        }

        // ====================================================
        // SORT CODE FORMATTING
        // ====================================================

        if (sortCode) {

            sortCode.addEventListener(
                "input",
                function () {

                    // --------------------------------------------
                    // Keep digits only.
                    // --------------------------------------------

                    let digits =
                        this.value.replace(
                            /\D/g,
                            ""
                        );

                    // --------------------------------------------
                    // Maximum six digits.
                    // --------------------------------------------

                    digits =
                        digits.substring(
                            0,
                            6
                        );

                    // --------------------------------------------
                    // Insert hyphens automatically:
                    //
                    // 12
                    // 12-34
                    // 12-34-56
                    // --------------------------------------------

                    let formatted =
                        "";

                    if (
                        digits.length <= 2
                    ) {

                        formatted =
                            digits;

                    } else if (
                        digits.length <= 4
                    ) {

                        formatted =
                            digits.substring(
                                0,
                                2
                            )
                            + "-"
                            + digits.substring(
                                2
                            );

                    } else {

                        formatted =
                            digits.substring(
                                0,
                                2
                            )
                            + "-"
                            + digits.substring(
                                2,
                                4
                            )
                            + "-"
                            + digits.substring(
                                4
                            );
                    }

                    this.value =
                        formatted;
                }
            );
        }

        // ====================================================
        // ACCOUNT NUMBER
        // ====================================================

        if (accountNumber) {

            accountNumber.addEventListener(
                "input",
                function () {

                    // Only digits.
                    this.value =
                        this.value.replace(
                            /\D/g,
                            ""
                        );

                    // Exactly eight maximum.
                    this.value =
                        this.value.substring(
                            0,
                            8
                        );
                }
            );
        }

        // ====================================================
        // DATE CLIENT-SIDE GUIDANCE
        // ====================================================

        if (accountOpenedDate) {

            accountOpenedDate.addEventListener(
                "change",
                function () {

                    const value =
                        this.value;

                    if (!value) {
                        return;
                    }

                    const selectedDate =
                        new Date(
                            value
                        );

                    const minimumDate =
                        new Date();

                    minimumDate.setMonth(
                        minimumDate.getMonth()
                        - 6
                    );

                    if (
                        selectedDate
                        > minimumDate
                    ) {

                        this.setCustomValidity(
                            "The bank account must have been open for at least six months."
                        );

                    } else {

                        this.setCustomValidity(
                            ""
                        );
                    }
                }
            );
        }

        // ====================================================
        // INITIAL STATE
        // ====================================================

        clearNextOfKin();

        toggleUI();
    }
);