document.addEventListener("DOMContentLoaded", function () {
  const causeSelect = document.getElementById("id_cause_type");
  const dependantWrapper = document.getElementById("dependant-wrapper");
  const dependantSelect = document.getElementById("id_causer_dependant");
  const claimerField = document.getElementById("id_claimer");
  const affectedField = document.getElementById("id_causer_full_name");

  const memberName = claimerField.dataset.member;
  const nokName = claimerField.dataset.nok;

  function updateForm() {
    const cause = causeSelect.value;

    // Who submits
    claimerField.value = memberName || nokName;

    if (cause === "member") {
      dependantWrapper.style.display = "none";
      dependantSelect.value = "";
      affectedField.value = memberName;
    } else {
      dependantWrapper.style.display = "block";
      const selected =
        dependantSelect.options[dependantSelect.selectedIndex]?.text || "";
      affectedField.value = selected;
    }
  }

  causeSelect.addEventListener("change", updateForm);
  dependantSelect.addEventListener("change", updateForm);

  updateForm();
});
