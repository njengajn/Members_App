/* =========================================================
   REGISTER STEP 1
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    const form = document.getElementById("registerStep1Form");

    if (form) {

        form.addEventListener("submit", function (e) {

            e.preventDefault();

            const formData = new FormData(form);

            fetch("/members/ajax/register/", {
                method: "POST",
                body: formData
            })
            .then(r => r.json())
            .then(data => {

                if (data.status === "ok") {

                    window.location.href =
                        "/members/register/verify-email/";

                } else {

                    alert(data.message || "Registration failed");

                }

            })
            .catch(error => {

                console.error(error);

                alert("Something went wrong.");

            });

        });

    }

});


/* =========================================================
   DEPENDANTS
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    const addBtn =
        document.getElementById("btnAddDep");

    const table =
        document.getElementById("dependantsTable");

    /* IMPORTANT FIX */
    if (!addBtn || !table) return;

    addBtn.addEventListener("click", function () {

        const name =
            prompt("Enter dependant name:");

        if (!name) return;

        const relationship =
            prompt("Enter relationship:");

        if (!relationship) return;

        const formData = new FormData();

        formData.append("name", name);

        formData.append("relationship", relationship);

        formData.append(
            "csrfmiddlewaretoken",
            document.querySelector(
                '[name=csrfmiddlewaretoken]'
            ).value
        );

        fetch("/members/ajax/dependants/add/", {
            method: "POST",
            body: formData
        })
        .then(r => r.json())
        .then(d => {

            if (d.status === "ok") {

                table.innerHTML += `
                    <tr>
                        <td>${d.name}</td>
                        <td>${d.relationship}</td>
                        <td>
                            <button
                                class="btn btn-danger btn-sm remove-btn"
                                data-id="${d.id}">
                                Remove
                            </button>
                        </td>
                    </tr>
                `;

            }

        });

    });


    table.addEventListener("click", function (e) {

        if (!e.target.classList.contains("remove-btn")) return;

        const id = e.target.dataset.id;

        const row = e.target.closest("tr");

        const formData = new FormData();

        formData.append("id", id);

        formData.append(
            "csrfmiddlewaretoken",
            document.querySelector(
                '[name=csrfmiddlewaretoken]'
            ).value
        );

        fetch("/members/ajax/dependants/remove/", {
            method: "POST",
            body: formData
        })
        .then(r => r.json())
        .then(d => {

            if (d.status === "ok") {

                row.remove();

            }

        });

    });

});


/* =========================================================
   CLAIM FORM UX
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    const causeType =
        document.getElementById("id_cause_type");

    if (!causeType) return;

    const dependantWrapper =
        document.getElementById("dependant-wrapper");

    const memberWrapper =
        document.getElementById("member-wrapper");

    const claimerTextarea =
        document.getElementById("id_claimer");

    const causerTextarea =
        document.getElementById("id_causer_full_name");

    function updateCauseUI() {

        if (causeType.value === "dependant") {

            dependantWrapper.style.display = "block";

            memberWrapper.style.display = "none";

            claimerTextarea.value =
                claimerTextarea.dataset.memberName || "";

            causerTextarea.value = "";

        }

        if (causeType.value === "member") {

            dependantWrapper.style.display = "none";

            memberWrapper.style.display = "block";

            claimerTextarea.value =
                claimerTextarea.dataset.nokName || "";

            causerTextarea.value = "";

        }

    }

    causeType.addEventListener("change", updateCauseUI);

    updateCauseUI();

});