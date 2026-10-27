// Caminho: web/js/auth.js
function exibirAlerta(mensagem, tipo = "error") {
    const alertBox = document.getElementById("auth-alert");
    if (!alertBox) return;
    alertBox.textContent = mensagem;
    alertBox.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    alertBox.style.display = "block";
}

function alternarAba(aba) {
    const formLogin = document.getElementById("form-login");
    const formRegister = document.getElementById("form-register");
    const tabLogin = document.getElementById("tab-login");
    const tabRegister = document.getElementById("tab-register");
    const alertBox = document.getElementById("auth-alert");

    if (alertBox) alertBox.style.display = "none";

    if (aba === "login") {
        formLogin.style.display = "block";
        formRegister.style.display = "none";
        tabLogin.classList.add("active");
        tabRegister.classList.remove("active");
    } else {
        formLogin.style.display = "none";
        formRegister.style.display = "block";
        tabLogin.classList.remove("active");
        tabRegister.classList.add("active");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const formLogin = document.getElementById("form-login");
    const formRegister = document.getElementById("form-register");

    if (formLogin) {
        formLogin.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = document.getElementById("login-email").value.trim();
            const senha = document.getElementById("login-senha").value;

            try {
                const response = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email, senha })
                });
                const data = await response.json();

                if (response.ok && data.sucesso) {
                    localStorage.setItem("usuario_logado", JSON.stringify(data.usuario));
                    window.location.href = "/pages/dashboard.html";
                } else {
                    exibirAlerta(data.erro || "Falha ao autenticar.");
                }
            } catch (err) {
                exibirAlerta("Erro de conexão com o servidor.");
            }
        });
    }

    if (formRegister) {
        formRegister.addEventListener("submit", async (e) => {
            e.preventDefault();
            const nome = document.getElementById("reg-nome").value.trim();
            const email = document.getElementById("reg-email").value.trim();
            const telefone_whatsapp = document.getElementById("reg-whatsapp").value.trim();
            const senha = document.getElementById("reg-senha").value;

            try {
                const response = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ nome, email, senha, telefone_whatsapp })
                });
                const data = await response.json();

                if (response.ok && data.sucesso) {
                    exibirAlerta("Conta criada com sucesso! Faça login.", "success");
                    alternarAba("login");
                } else {
                    exibirAlerta(data.erro || "Erro ao cadastrar usuário.");
                }
            } catch (err) {
                exibirAlerta("Erro de conexão com o servidor.");
            }
        });
    }
});

async function realizarLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    localStorage.removeItem("usuario_logado");
    window.location.href = "/";
}