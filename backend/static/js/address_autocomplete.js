/**
 * Address Autocomplete Script
 * - Fetches suggestions from backend
 * - Displays dropdown
 * - Populates fields on selection
 */

function initAddressAutocomplete() {

    const input = document.getElementById("line_1");
    const dropdown = document.getElementById("address-dropdown");

    input.addEventListener("input", function () {
        const query = input.value;

        if (query.length < 3) {
            dropdown.innerHTML = "";
            return;
        }

        fetch(`/api/address-autocomplete/?q=${query}`)
            .then(res => res.json())
            .then(data => {

                dropdown.innerHTML = "";

                data.results.forEach(addr => {

                    const item = document.createElement("div");
                    item.classList.add("list-group-item", "list-group-item-action");

                    item.innerText = addr.label;

                    item.onclick = function () {

                        // Populate fields
                        document.getElementById("house_number").value = addr.house_number;
                        document.getElementById("line_1").value = addr.line_1;
                        document.getElementById("line_2").value = addr.line_2;
                        document.getElementById("town").value = addr.town;
                        document.getElementById("county").value = addr.county;
                        document.getElementById("postcode").value = addr.postcode;
                        document.getElementById("country").value = addr.country;

                        dropdown.innerHTML = "";
                    };

                    dropdown.appendChild(item);
                });

            });
    });
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", initAddressAutocomplete);