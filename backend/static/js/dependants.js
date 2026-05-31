console.log("DEPENDANTS JS LOADED");


(function () {

    console.log("INIT RUNNING");

    const addBtn = document.getElementById("addDepBtn");
    const container = document.getElementById("dependantsList");

    if (!addBtn || !container) {
        console.log("❌ Elements not found");
        return;
    }

    let count = container.querySelectorAll(".dependant-item").length;

    addBtn.addEventListener("click", function () {

    count++;

    const div = document.createElement("div");

    div.className = "dependant-item mb-3 border p-3 rounded";
    div.style.opacity = "0";
    div.style.transform = "translateY(10px)";
    div.style.transition = "all 0.3s ease";

    div.innerHTML = `
        <div class="mb-2"><strong>Dependant ${count}</strong></div>

        <input name="dep_${count}_first" class="form-control mb-1" placeholder="First name" required>
        <input name="dep_${count}_middle" class="form-control mb-1" placeholder="Middle name">
        <input name="dep_${count}_surname" class="form-control mb-1" placeholder="Surname" required>

        <input type="date" name="dep_${count}_dob" class="form-control mb-1">

        <select name="dep_${count}_relation" class="form-select mb-1">
            <option value="CHILD">Child</option>
            <option value="SPOUSE">Spouse</option>
            <option value="SIBLING">Sibling</option>
            <option value="PARENT">Parent</option>
            <option value="OTHER">Other</option>
        </select>

        <button type="button" class="btn btn-sm btn-danger mt-2 remove-dep">
            Remove
        </button>
    `;

    container.appendChild(div);

    // animate in
    setTimeout(() => {
        div.style.opacity = "1";
        div.style.transform = "translateY(0)";
    }, 10);
});

    // REMOVE DEPENDANT
    container.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-dep")) {

        const item = e.target.closest(".dependant-item");

        item.style.opacity = "0";
        item.style.transform = "translateY(-10px)";

        setTimeout(() => item.remove(), 300);
    }
});

})();