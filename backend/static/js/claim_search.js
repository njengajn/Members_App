// backend/static/js/claim_search.js

document.addEventListener("DOMContentLoaded", function () {

    console.log("Claim JS loaded");

    const causeType =
        document.getElementById("id_cause_type");

    const dependantSelect =
        document.getElementById("id_causer_dependant");

    const searchWrapper =
        document.getElementById("member-search-wrapper");

    const dependantWrapper =
        document.getElementById("dependant-wrapper");

    const searchInput =
        document.getElementById("member-search");

    const results =
        document.getElementById("search-results");

    const hiddenInput =
        document.getElementById("selected_member_id");

    const affected =
        document.getElementById("affected-person");

    const fileInput =
        document.getElementById("file-input");

    const fileList =
        document.getElementById("file-list");

    const dropZone =
        document.getElementById("drop-zone");


    // =========================================================
    // CLAIM TYPE UI
    // =========================================================

    function toggleUI() {

        if (!causeType) {
            return;
        }

        if (causeType.value === "member") {

            searchWrapper.style.display =
                "block";

            dependantWrapper.style.display =
                "none";

        } else {

            searchWrapper.style.display =
                "none";

            dependantWrapper.style.display =
                "block";

            if (hiddenInput) {
                hiddenInput.value = "";
            }
        }
    }


    if (causeType) {

        causeType.addEventListener(
            "change",
            toggleUI
        );

        toggleUI();
    }


    // =========================================================
    // DEPENDANT → AFFECTED PERSON
    // =========================================================

    if (dependantSelect) {

        dependantSelect.addEventListener(
            "change",
            function () {

                if (
                    !this.value ||
                    this.selectedIndex < 0
                ) {

                    affected.value = "";
                    return;
                }

                affected.value =
                    this.options[
                        this.selectedIndex
                    ].text;
            }
        );
    }


    // =========================================================
    // MEMBER SEARCH
    // =========================================================

    if (searchInput) {

        searchInput.addEventListener(
            "keyup",
            function () {

                const query =
                    this.value.trim();


                // -------------------------------------------------
                // Do not search for very short text.
                // -------------------------------------------------

                if (query.length < 2) {

                    results.innerHTML = "";

                    return;
                }


                // -------------------------------------------------
                // Search active members.
                // -------------------------------------------------

                fetch(
                    `/admin-panel/claims/search-members/?q=${encodeURIComponent(query)}`
                )

                    .then(function (response) {

                        if (!response.ok) {

                            throw new Error(
                                "Member search failed."
                            );
                        }

                        return response.json();
                    })

                    .then(function (data) {

                        results.innerHTML = "";


                        if (!data.length) {

                            const empty =
                                document.createElement("div");

                            empty.classList.add(
                                "list-group-item",
                                "text-muted"
                            );

                            empty.innerText =
                                "No active members found.";

                            results.appendChild(
                                empty
                            );

                            return;
                        }


                        data.forEach(function (member) {

                            const item =
                                document.createElement("button");

                            item.type =
                                "button";

                            item.classList.add(
                                "list-group-item",
                                "list-group-item-action",
                                "text-start"
                            );


                            // -----------------------------------------
                            // MEMBER DETAILS
                            // -----------------------------------------

                            const uid =
                                member.uid ||
                                "N/A";

                            const email =
                                member.email ||
                                "No email";

                            const phone =
                                member.phone ||
                                "";


                            // -----------------------------------------
                            // DISPLAY
                            // -----------------------------------------

                            item.innerHTML = `

                                <div class="fw-semibold">
                                    ${member.name}
                                </div>

                                <div class="small text-muted">
                                    UID: ${uid}
                                </div>

                                <div class="small text-muted">
                                    ${email}
                                </div>

                                ${
                                    phone
                                        ? `
                                            <div class="small text-muted">
                                                ${phone}
                                            </div>
                                        `
                                        : ""
                                }

                            `;


                            // -----------------------------------------
                            // SELECT MEMBER
                            // -----------------------------------------

                            item.addEventListener(
                                "click",
                                function () {

                                    hiddenInput.value =
                                        member.id;


                                    affected.value =
                                        `${member.name} — Member UID: ${uid}`;


                                    searchInput.value =
                                        `${member.name} — ${uid}`;


                                    results.innerHTML = "";
                                }
                            );


                            results.appendChild(
                                item
                            );

                        });

                    })

                    .catch(function (error) {

                        console.error(
                            "Member search error:",
                            error
                        );

                        results.innerHTML = `
                            <div class="list-group-item text-danger">
                                Unable to search members.
                                Please try again.
                            </div>
                        `;
                    });

            }
        );
    }


    // =========================================================
    // FILE HANDLING
    // =========================================================

    function createPreview(file) {

        const container =
            document.createElement("div");

        container.classList.add(
            "border",
            "rounded",
            "p-2",
            "mb-2",
            "bg-white"
        );


        // -----------------------------------------------------
        // IMAGE PREVIEW
        // -----------------------------------------------------

        let preview = "";

        if (
            file.type &&
            file.type.startsWith("image")
        ) {

            preview = `
                <img
                    src="${URL.createObjectURL(file)}"
                    alt="Document preview"
                    class="img-fluid rounded mb-2"
                    style="
                        max-width: 120px;
                        max-height: 120px;
                    "
                >
            `;
        }


        const progressId =
            "progress_" +
            Math.random()
                .toString(36)
                .substr(2, 9);


        container.innerHTML = `

            ${preview}

            <div class="fw-semibold">
                ${file.name}
            </div>

            <div class="small text-muted">
                ${(file.size / 1024).toFixed(1)} KB
            </div>

            <input
                type="text"
                name="doc_title"
                placeholder="Document title"
                class="form-control mt-2"
            >

            <textarea
                name="doc_description"
                placeholder="Document description"
                class="form-control mt-2"
                rows="2"
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


    // =========================================================
    // SIMULATED PROGRESS
    // =========================================================

    function simulateProgress(id) {

        let progress = 0;

        const bar =
            document.getElementById(id);


        const interval =
            setInterval(function () {

                progress += 10;


                if (bar) {

                    bar.style.width =
                        progress + "%";

                    bar.innerText =
                        progress + "%";
                }


                if (progress >= 100) {

                    clearInterval(
                        interval
                    );
                }

            }, 100);
    }


    // =========================================================
    // PROCESS FILES
    // =========================================================

    function handleFiles(files) {

        Array.from(files).forEach(
            function (file) {

                createPreview(file);

            }
        );
    }


    // =========================================================
    // FILE INPUT
    // =========================================================

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


    // =========================================================
    // DRAG AND DROP
    // =========================================================

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

});