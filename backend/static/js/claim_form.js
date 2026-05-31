// ============================================
// CLAIM FORM UX
// ============================================

document.addEventListener("DOMContentLoaded", function () {

    const causeType = document.getElementById("id_cause_type");
    if (!causeType) return; // only runs on claim page

    const dependantWrapper = document.getElementById("dependant-wrapper");
    const memberWrapper = document.getElementById("member-wrapper");

    const claimerTextarea = document.getElementById("id_claimer");
    const causerTextarea = document.getElementById("id_causer_full_name");

    function updateCauseUI() {

        if (causeType.value === "dependant") {
            dependantWrapper.style.display = "block";
            memberWrapper.style.display = "none";

            claimerTextarea.value = claimerTextarea.dataset.memberName || "";
            causerTextarea.value = "";
        }

        if (causeType.value === "member") {
            dependantWrapper.style.display = "none";
            memberWrapper.style.display = "block";

            claimerTextarea.value = claimerTextarea.dataset.nokName || "";
            causerTextarea.value = "";
        }
    }

    causeType.addEventListener("change", updateCauseUI);
    updateCauseUI();

});
