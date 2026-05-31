document.addEventListener("DOMContentLoaded", function () {

    const requestType = document.getElementById("request_type");
    const memberWrapper = document.getElementById("member-wrapper");

    if (!requestType) return;

    function toggleMemberField() {
        if (requestType.value === "Claim") {
            memberWrapper.style.display = "block";
        } else {
            memberWrapper.style.display = "none";
        }
    }

    requestType.addEventListener("change", toggleMemberField);

    // Initial check
    toggleMemberField();
});