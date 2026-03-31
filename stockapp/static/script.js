// Load products from Django API
async function loadProducts() {

    const response = await fetch("/api/products/");
    const products = await response.json();

    const tableBody = document.querySelector("#inventoryTable tbody");

    let total = 0;
    let low = 0;
    let critical = 0;

    tableBody.innerHTML = "";

    products.forEach(product => {

        total++;

        if (product.status === "Low") low++;
        if (product.status === "Critical") critical++;

        tableBody.innerHTML += `
            <tr>
                <td>${product.name}</td>
                <td>${product.category}</td>
                <td>${product.stock}</td>
                <td class="${product.status.toLowerCase()}">
                    ${product.status}
                </td>
            </tr>
        `;
    });

    document.getElementById("total").innerText = total;
    document.getElementById("low").innerText = low;
    document.getElementById("critical").innerText = critical;
}

document.addEventListener("DOMContentLoaded", loadProducts);