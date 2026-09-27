/**
 * ================================================================
 * POSTCODE LOOKUP
 * ================================================================
 *
 * Registration address assistance.
 *
 * IMPORTANT:
 * - This is an OPTIONAL convenience feature.
 * - Manual address entry remains fully supported.
 * - Registration does NOT depend on this lookup working.
 * - The browser communicates only with our Django endpoint:
 *
 *       /api/postcode-lookup/
 *
 * - Django communicates with Postcodes.io.
 *
 * Postcodes.io provides postcode/geographic information.
 * It does NOT provide individual property addresses.
 *
 * Therefore this script only assists with:
 *
 *       Town / City
 *       County
 *       Country
 *
 * The member still enters:
 *
 *       House number/name
 *       Address Line 1
 *       Address Line 2
 *       Postcode
 *
 * manually.
 * ================================================================
 */


/**
 * ================================================================
 * LOOK UP POSTCODE
 * ================================================================
 *
 * This function can be called from a button beside the postcode
 * field.
 *
 * It is deliberately defensive:
 * - Missing fields do not cause a JavaScript error.
 * - API failure does not prevent registration.
 * - Existing manually entered values are not destroyed when the
 *   lookup fails.
 */
function lookupPostcode() {

    const postcodeInput =
        document.getElementById("postcode");


    /*
     * ------------------------------------------------------------
     * Safety check
     * ------------------------------------------------------------
     *
     * This file may be loaded on another page in the future.
     * Do nothing if the postcode field does not exist.
     */
    if (!postcodeInput) {
        return;
    }


    const postcode =
        postcodeInput.value.trim();


    /*
     * ------------------------------------------------------------
     * Validate postcode input
     * ------------------------------------------------------------
     */
    if (!postcode) {

        alert(
            "Please enter a postcode first."
        );

        postcodeInput.focus();

        return;
    }


    /*
     * ------------------------------------------------------------
     * Optional feedback element
     * ------------------------------------------------------------
     *
     * The template may contain:
     *
     *     id="postcode-lookup-status"
     *
     * If it does not, the lookup still works.
     */
    const status =
        document.getElementById(
            "postcode-lookup-status"
        );


    if (status) {

        status.textContent =
            "Looking up postcode…";

        status.classList.remove(
            "text-danger",
            "text-success"
        );

        status.classList.add(
            "text-muted"
        );
    }


    /*
     * ------------------------------------------------------------
     * Call our Django endpoint
     * ------------------------------------------------------------
     *
     * The external Postcodes.io service is deliberately NOT
     * called directly from the browser.
     *
     * This keeps the external service behind our application
     * and allows the lookup provider to be changed later without
     * changing the registration JavaScript.
     */
    fetch(
        `/api/postcode-lookup/?postcode=${encodeURIComponent(postcode)}`,
        {
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        }
    )

        .then(function (response) {

            /*
             * A 404/400/500 response is handled as a failed
             * optional lookup rather than a registration failure.
             */
            if (!response.ok) {

                throw new Error(
                    `Postcode lookup failed: ${response.status}`
                );
            }

            return response.json();
        })

        .then(function (data) {

            /*
             * ----------------------------------------------------
             * Successful lookup
             * ----------------------------------------------------
             */
            if (data.success) {

                const town =
                    document.getElementById("town");

                const county =
                    document.getElementById("county");

                const country =
                    document.getElementById("country");


                /*
                 * Only populate fields when the API supplied a
                 * value.
                 *
                 * This avoids replacing an existing manually
                 * entered value with an empty string.
                 */
                if (
                    town &&
                    data.town
                ) {

                    town.value =
                        data.town;
                }


                if (
                    county &&
                    data.county
                ) {

                    county.value =
                        data.county;
                }


                if (
                    country &&
                    data.country
                ) {

                    country.value =
                        data.country;
                }


                /*
                 * Optional success message.
                 */
                if (status) {

                    status.textContent =
                        "Postcode information found.";

                    status.classList.remove(
                        "text-muted",
                        "text-danger"
                    );

                    status.classList.add(
                        "text-success"
                    );
                }


                return;
            }


            /*
             * ----------------------------------------------------
             * Lookup returned no valid postcode
             * ----------------------------------------------------
             *
             * This is NOT a registration failure.
             *
             * The member can continue entering the address
             * manually.
             */
            if (status) {

                status.textContent =
                    "Postcode not found. Please enter the address manually.";

                status.classList.remove(
                    "text-muted",
                    "text-success"
                );

                status.classList.add(
                    "text-danger"
                );

            } else {

                alert(
                    "Postcode not found. Please enter the address manually."
                );
            }
        })

        .catch(function (error) {

            /*
             * ----------------------------------------------------
             * External service / network failure
             * ----------------------------------------------------
             *
             * IMPORTANT:
             *
             * Never block registration because Postcodes.io
             * cannot be reached.
             */
            console.error(
                "Postcode lookup error:",
                error
            );


            if (status) {

                status.textContent =
                    "Postcode lookup unavailable. Please enter the address manually.";

                status.classList.remove(
                    "text-muted",
                    "text-success"
                );

                status.classList.add(
                    "text-danger"
                );

            } else {

                alert(
                    "Postcode lookup unavailable. Please enter the address manually."
                );
            }
        });
}