/**
 * ================================================================
 * ADDRESS AUTOCOMPLETE
 * ================================================================
 *
 * Registration address lookup.
 *
 * Behaviour:
 * - Watches the postcode search field.
 * - Requests address suggestions from the Django backend.
 * - Displays the returned addresses in a dropdown.
 * - Populates the existing registration address fields when an
 *   address is selected.
 *
 * IMPORTANT:
 * - The API key is NOT exposed here.
 * - The browser only communicates with our Django endpoint:
 *
 *       /api/address-autocomplete/
 *
 * - The existing field IDs are deliberately retained:
 *
 *       house_number
 *       line_1
 *       line_2
 *       town
 *       county
 *       postcode
 *       country
 *
 * This prevents changes to the registration session structure
 * and avoids unnecessary regression in the registration flow.
 * ================================================================
 */


/**
 * ================================================================
 * INITIALISE ADDRESS AUTOCOMPLETE
 * ================================================================
 */
function initAddressAutocomplete() {

    /*
     * ------------------------------------------------------------
     * Locate the postcode search field.
     * ------------------------------------------------------------
     *
     * The registration template should contain:
     *
     *     id="postcode"
     *
     * If the field is not present, there is nothing for this
     * script to initialise.
     */
    const postcodeInput = document.getElementById("postcode");

    /*
     * The dropdown is populated by this script.
     *
     * Expected template element:
     *
     *     id="address-dropdown"
     */
    const dropdown = document.getElementById("address-dropdown");


    /*
     * ------------------------------------------------------------
     * Safety check
     * ------------------------------------------------------------
     *
     * This script is deliberately safe if loaded on another page
     * that does not contain the registration address fields.
     */
    if (!postcodeInput || !dropdown) {
        return;
    }


    /**
     * ============================================================
     * CLEAR DROPDOWN
     * ============================================================
     *
     * Keeping this in one function avoids repeating DOM cleanup
     * throughout the script.
     */
    function clearDropdown() {

        dropdown.innerHTML = "";

        /*
         * Hide the dropdown after clearing it.
         */
        dropdown.style.display = "none";
    }


    /**
     * ============================================================
     * SHOW DROPDOWN
     * ============================================================
     */
    function showDropdown() {

        dropdown.style.display = "block";
    }


    /**
     * ============================================================
     * POPULATE ADDRESS FIELDS
     * ============================================================
     *
     * The API returns the existing structured address fields.
     *
     * We deliberately use the existing field IDs rather than
     * introducing new field names.
     */
    function populateAddress(address) {

        const houseNumber =
            document.getElementById("house_number");

        const line1 =
            document.getElementById("line_1");

        const line2 =
            document.getElementById("line_2");

        const town =
            document.getElementById("town");

        const county =
            document.getElementById("county");

        const postcode =
            document.getElementById("postcode");

        const country =
            document.getElementById("country");


        /*
         * --------------------------------------------------------
         * Populate only fields that actually exist.
         * --------------------------------------------------------
         *
         * This makes the script tolerant of small template
         * differences and prevents JavaScript errors from stopping
         * the rest of the registration page.
         */

        if (houseNumber) {
            houseNumber.value =
                address.house_number || "";
        }

        if (line1) {
            line1.value =
                address.line_1 || "";
        }

        if (line2) {
            line2.value =
                address.line_2 || "";
        }

        if (town) {
            town.value =
                address.town || "";
        }

        if (county) {
            county.value =
                address.county || "";
        }

        if (postcode) {
            postcode.value =
                address.postcode || "";
        }

        if (country) {
            country.value =
                address.country || "UK";
        }


        /*
         * --------------------------------------------------------
         * Close the results after an address has been selected.
         * --------------------------------------------------------
         */
        clearDropdown();
    }


    /**
     * ============================================================
     * CREATE ADDRESS RESULT
     * ============================================================
     *
     * Creates one selectable address item.
     *
     * We use a <button> rather than an arbitrary clickable <div>.
     * This gives the results better keyboard/accessibility
     * behaviour and avoids relying on inline event handlers.
     */
    function createAddressResult(address) {

        const item =
            document.createElement("button");


        /*
         * Make the button behave like a normal dropdown item.
         */
        item.type = "button";

        item.classList.add(
            "list-group-item",
            "list-group-item-action"
        );


        /*
         * Use textContent rather than innerHTML.
         *
         * This prevents address data returned by the API from
         * being interpreted as HTML.
         */
        item.textContent =
            address.label || "";


        /*
         * --------------------------------------------------------
         * Address selection
         * --------------------------------------------------------
         */
        item.addEventListener(
            "click",
            function () {

                populateAddress(address);

            }
        );


        return item;
    }


    /**
     * ============================================================
     * SEARCH ADDRESSES
     * ============================================================
     */
    function searchAddresses(query) {

        /*
         * Remove leading/trailing whitespace before sending the
         * query to the backend.
         */
        const cleanedQuery =
            query.trim();


        /*
         * Do not make unnecessary requests for very short input.
         *
         * Three characters is the same minimum threshold used by
         * the previous autocomplete implementation.
         */
        if (cleanedQuery.length < 3) {

            clearDropdown();

            return;
        }


        /*
         * --------------------------------------------------------
         * Encode the query.
         * --------------------------------------------------------
         *
         * This is important because postcode/address searches may
         * contain spaces and other characters.
         */
        const url =
            `/api/address-autocomplete/?q=${encodeURIComponent(
                cleanedQuery
            )}`;


        /*
         * Show a small loading indication while the backend
         * retrieves the addresses.
         */
        dropdown.innerHTML = "";

        const loadingItem =
            document.createElement("div");

        loadingItem.classList.add(
            "list-group-item",
            "text-muted"
        );

        loadingItem.textContent =
            "Searching for addresses…";

        dropdown.appendChild(
            loadingItem
        );

        showDropdown();


        /*
         * --------------------------------------------------------
         * Request addresses from Django.
         * --------------------------------------------------------
         */
        fetch(url, {
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        })

            .then(function (response) {

                /*
                 * HTTP errors are handled explicitly rather than
                 * attempting to process an error response as a
                 * successful address list.
                 */
                if (!response.ok) {

                    throw new Error(
                        `Address lookup failed: ${response.status}`
                    );
                }

                return response.json();
            })

            .then(function (data) {

                /*
                 * Clear the loading message before displaying the
                 * actual results.
                 */
                dropdown.innerHTML = "";


                /*
                 * Defensive check.
                 *
                 * The expected API response is:
                 *
                 * {
                 *     "results": [...]
                 * }
                 */
                if (
                    !data ||
                    !Array.isArray(data.results)
                ) {

                    clearDropdown();

                    return;
                }


                /*
                 * No addresses found.
                 */
                if (data.results.length === 0) {

                    const noResults =
                        document.createElement("div");

                    noResults.classList.add(
                        "list-group-item",
                        "text-muted"
                    );

                    noResults.textContent =
                        "No addresses found.";

                    dropdown.appendChild(
                        noResults
                    );

                    showDropdown();

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Display returned addresses.
                 * ------------------------------------------------
                 */
                data.results.forEach(
                    function (address) {

                        const item =
                            createAddressResult(
                                address
                            );

                        dropdown.appendChild(
                            item
                        );
                    }
                );


                showDropdown();
            })

            .catch(function (error) {

                /*
                 * Do not expose technical API details to the user.
                 *
                 * The error is logged for debugging while the
                 * registration page receives a simple message.
                 */
                console.error(
                    "Address autocomplete error:",
                    error
                );


                dropdown.innerHTML = "";


                const errorItem =
                    document.createElement("div");

                errorItem.classList.add(
                    "list-group-item",
                    "text-danger"
                );

                errorItem.textContent =
                    "Unable to search for addresses. Please enter the address manually.";

                dropdown.appendChild(
                    errorItem
                );

                showDropdown();
            });
    }


    /**
     * ============================================================
     * POSTCODE INPUT
     * ============================================================
     *
     * Search when the user changes the postcode field.
     *
     * A short debounce prevents a request from being sent for
     * every single keystroke.
     */
    let searchTimer = null;


    postcodeInput.addEventListener(
        "input",
        function () {

            /*
             * Cancel the previous pending search.
             */
            if (searchTimer) {

                clearTimeout(
                    searchTimer
                );
            }


            /*
             * Clear immediately when the user has entered too
             * little information.
             */
            if (
                postcodeInput.value.trim().length < 3
            ) {

                clearDropdown();

                return;
            }


            /*
             * Wait briefly before making the request.
             *
             * This prevents unnecessary API calls while the user
             * is still typing.
             */
            searchTimer =
                setTimeout(
                    function () {

                        searchAddresses(
                            postcodeInput.value
                        );

                    },
                    300
                );
        }
    );


    /**
     * ============================================================
     * CLOSE DROPDOWN WHEN CLICKING OUTSIDE
     * ============================================================
     *
     * This keeps the registration form clean after the user has
     * finished interacting with the results.
     */
    document.addEventListener(
        "click",
        function (event) {

            /*
             * If the click occurred inside the postcode field or
             * dropdown, leave the dropdown alone.
             */
            if (
                postcodeInput.contains(
                    event.target
                ) ||
                dropdown.contains(
                    event.target
                )
            ) {

                return;
            }


            clearDropdown();
        }
    );


    /**
     * ============================================================
     * KEYBOARD ESCAPE
     * ============================================================
     *
     * Allows the user to dismiss the results with Escape.
     */
    postcodeInput.addEventListener(
        "keydown",
        function (event) {

            if (event.key === "Escape") {

                clearDropdown();
            }
        }
    );
}


/**
 * ================================================================
 * PAGE INITIALISATION
 * ================================================================
 *
 * Wait until the registration template has loaded before looking
 * for the address fields.
 * ================================================================
 */
document.addEventListener(
    "DOMContentLoaded",
    initAddressAutocomplete
);