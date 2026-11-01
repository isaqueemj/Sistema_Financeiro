// Caminho: web/js/auth.js
let identificadorPendente2FA = "";

document.addEventListener("DOMContentLoaded", () => {
    configurarBotoesOlhoSenha();
    configurarAlternanciaTelas();
    configurarFormularioLogin();
    configurarFormularioCadastro();
    configurarEventos2FA();
});

function exibirAlerta(mensagem, tipo = "erro") {
    const seletores = [
        "#auth-alert",
        "#login-alert",
        ".alert-box",
        ".erro-banner",
        "[role='alert']"
    ];
    let caixa = null;
    for (const sel of seletores) {
        const el = document.querySelector(sel);
        if (el) {
            caixa = el;
            break;
        }
    }

    if (!caixa) {
        // Procura pela div vermelha existente ou cria uma acima do título
        const formLogin = document.querySelector("form");
        caixa = document.createElement("div");
        caixa.id = "auth-alert";
        caixa.style.padding = "12px 16px";
        caixa.style.borderRadius = "8px";
        caixa.style.marginBottom = "16px";
        caixa.style.fontSize = "14px";
        if (formLogin && formLogin.parentElement) {
            formLogin.parentElement.insertBefore(caixa, formLogin);
        }
    }

    caixa.style.display = "block";
    if (tipo === "sucesso") {
        caixa.style.backgroundColor = "rgba(16, 185, 129, 0.15)";
        caixa.style.border = "1px solid rgba(16, 185, 129, 0.45)";
        caixa.style.color = "#6ee7b7";
    } else {
        caixa.style.backgroundColor = "rgba(239, 68, 68, 0.15)";
        caixa.style.border = "1px solid rgba(239, 68, 68, 0.45)";
        caixa.style.color = "#fca5a5";
    }
    caixa.textContent = mensagem;
}

function limparAlerta() {
    const caixa = document.querySelector("#auth-alert, #login-alert, .alert-box");
    if (caixa) caixa.style.display = "none";
}

function configurarBotoesOlhoSenha() {
    document.querySelectorAll(".toggle-password, [data-toggle-password]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const input = btn.parentElement.querySelector("input");
            if (!input) return;
            input.type = input.type === "password" ? "text" : "password";
        });
    });
}

function configurarAlternanciaTelas() {
    const btnCriarConta = document.getElementById("btn-show-register") ||
        Array.from(document.querySelectorAll("button, a")).find(
            (el) => el.textContent.trim().toUpperCase() === "CRIAR CONTA"
        );

    const btnVoltarLogin = document.getElementById("btn-show-login") ||
        Array.from(document.querySelectorAll("button, a")).find(
            (el) => el.textContent.trim().toUpperCase().includes("JÁ TENHO CONTA") ||
                    el.textContent.trim().toUpperCase().includes("FAZER LOGIN")
        );

    const viewLogin = document.getElementById("login-view") || document.getElementById("form-login");
    const viewRegister = document.getElementById("register-view") || document.getElementById("form-register");

    if (btnCriarConta && viewLogin && viewRegister) {
        btnCriarConta.addEventListener("click", (e) => {
            e.preventDefault();
            limparAlerta();
            viewLogin.style.display = "none";
            viewRegister.style.display = "block";
        });
    }

    if (btnVoltarLogin && viewLogin && viewRegister) {
        btnVoltarLogin.addEventListener("click", (e) => {
            e.preventDefault();
            limparAlerta();
            viewRegister.style.display = "none";
            viewLogin.style.display = "block";
        });
    }
}

function configurarFormularioLogin() {
    const formLogin = document.getElementById("form-login") || document.querySelector("form");
    if (!formLogin) return;

    formLogin.addEventListener("submit", async (e) => {
        e.preventDefault();
        limparAlerta();

        const inputIdent =
            document.getElementById("login-identificador") ||
            document.getElementById("login-email") ||
            formLogin.querySelector("input[type='text'], input[type='email']");
        const inputSenha =
            document.getElementById("login-senha") ||
            formLogin.querySelector("input[type='password']");

        const identificador = inputIdent ? inputIdent.value.trim() : "";
        const senha = inputSenha ? inputSenha.value : "";

        if (!identificador || !senha) {
            exibirAlerta("Preencha seu E-mail/@Telegram e sua senha.");
            return;
        }

        let res;
        let data;
        try {
            res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ identificador, email: identificador, senha })
            });
            data = await res.json();
        } catch (networkErr) {
            console.error("Erro na requisição /api/auth/login:", networkErr);
            exibirAlerta("Erro de comunicação com o servidor Flask. Verifique se o backend está ativo.");
            return;
        }

        if (!res.ok || !data.sucesso) {
            exibirAlerta(data.erro || "Credenciais inválidas.");
            return;
        }

        if (data.requer_2fa) {
            identificadorPendente2FA = data.identificador || identificador;
            abrirTelaVerificacao2FA(data.email_mascarado || identificador, data.aviso_smtp);
            return;
        }

        if (data.usuario) {
            localStorage.setItem("usuario_logado", JSON.stringify(data.usuario));
        }
        window.location.href = "/pages/dashboard.html";
    });
}

function abrirTelaVerificacao2FA(emailMascarado, avisoSmtp) {
    let container2FA = document.getElementById("view-2fa") || document.getElementById("step-2fa");
    const formLogin = document.getElementById("form-login") || document.querySelector("form");

    if (formLogin) {
        formLogin.style.display = "none";
    }

    // Se o HTML não tiver o container 2FA pronto, cria dinamicamente sem quebrar
    if (!container2FA) {
        container2FA = document.createElement("div");
        container2FA.id = "view-2fa";
        container2FA.style.marginTop = "16px";
        container2FA.innerHTML = `
            <h3 style="color:#f8fafc; font-size:20px; margin-bottom:8px;">Confirme seu 1º acesso (2FA)</h3>
            <p id="texto-email-2fa" style="color:#94a3b8; font-size:14px; margin-bottom:16px;"></p>
            <input id="input-codigo-2fa" type="text" maxlength="6" placeholder="Digite os 6 dígitos"
                style="width:100%; padding:12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:20px; letter-spacing:8px; text-align:center; margin-bottom:14px;" />
            <button id="btn-confirmar-2fa" type="button"
                style="width:100%; padding:12px; border-radius:8px; border:none; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; margin-bottom:10px;">
                VALIDAR CÓDIGO 2FA →
            </button>
            <button id="btn-reenviar-2fa" type="button"
                style="width:100%; padding:10px; border-radius:8px; border:1px solid #334155; background:transparent; color:#93c5fd; cursor:pointer;">
                Reenviar código por e-mail
            </button>
        `;
        if (formLogin && formLogin.parentElement) {
            formLogin.parentElement.appendChild(container2FA);
        } else {
            document.body.appendChild(container2FA);
        }
        configurarEventos2FA();
    }

    container2FA.style.display = "block";
    const infoEmail = document.getElementById("texto-email-2fa") || document.getElementById("email-mascarado-2fa");
    if (infoEmail) {
        infoEmail.textContent = `Enviamos um código de 6 dígitos para ${emailMascarado}. (Confira também o terminal do VS Code caso o SMTP não esteja configurado).`;
    }

    if (avisoSmtp) {
        exibirAlerta(avisoSmtp, "sucesso");
    } else {
        exibirAlerta(`Código 2FA enviado para ${emailMascarado}!`, "sucesso");
    }
}

function configurarEventos2FA() {
    const btnConfirmar = document.getElementById("btn-confirmar-2fa") || document.getElementById("btn-verify-2fa");
    if (btnConfirmar && !btnConfirmar.dataset.bound) {
        btnConfirmar.dataset.bound = "1";
        btnConfirmar.addEventListener("click", async (e) => {
            e.preventDefault();
            let codigo = "";
            const inputUnico = document.getElementById("input-codigo-2fa");
            if (inputUnico) {
                codigo = inputUnico.value.trim();
            } else {
                document.querySelectorAll(".otp-input, .digito-2fa").forEach((inp) => {
                    codigo += inp.value.trim();
                });
            }

            if (codigo.length < 6) {
                exibirAlerta("Digite o código completo de 6 dígitos.");
                return;
            }

            try {
                const res = await fetch("/api/auth/verificar-2fa", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        identificador: identificadorPendente2FA,
                        codigo
                    })
                });
                if (res.ok && data.sucesso) {
                    localStorage.setItem("usuario_logado", JSON.stringify(data.usuario || {}));
                    exibirAlerta("auth-alert", "2FA confirmado com sucesso! Redirecionando...", "success");
                    
                    // REDIRECIONAMENTO CORRETO PARA O DASHBOARD
                    setTimeout(() => {
                        window.location.href = "/pages/dashboard.html";
                    }, 800);
                } else {
                    exibirAlerta("auth-alert", data.erro || "Código 2FA incorreto ou expirado.", "error");
                }
                window.location.href = "/pages/dashboard.html";
            } catch (err) {
                exibirAlerta("Erro ao validar o código 2FA no servidor.");
            }
        });
    }

    const btnReenviar = document.getElementById("btn-reenviar-2fa");
    if (btnReenviar && !btnReenviar.dataset.bound) {
        btnReenviar.dataset.bound = "1";
        btnReenviar.addEventListener("click", async () => {
            try {
                const res = await fetch("/api/auth/reenviar-2fa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identificador: identificadorPendente2FA })
                });
                const data = await res.json();
                if (res.ok && data.sucesso) {
                    exibirAlerta("Novo código de 6 dígitos enviado! Confira seu e-mail ou terminal.", "sucesso");
                } else {
                    exibirAlerta(data.erro || "Não foi possível reenviar o código.");
                }
            } catch (err) {
                exibirAlerta("Falha ao solicitar novo código 2FA.");
            }
        });
    }
}

function configurarFormularioCadastro() {
    const formReg = document.getElementById("form-register");
    if (!formReg) return;

    formReg.addEventListener("submit", async (e) => {
        e.preventDefault();
        limparAlerta();

        const nome = (document.getElementById("reg-nome")?.value || "").trim();
        const email = (document.getElementById("reg-email")?.value || "").trim();
        let telegram = (
            document.getElementById("reg-telegram")?.value ||
            document.getElementById("register-telegram")?.value ||
            formReg.querySelector("input[name='telegram'], input[placeholder*='Telegram'], input[placeholder*='@']")?.value ||
            ""
        ).trim();
        const telegram_id = (document.getElementById("reg-telegram-id")?.value || "").trim();
        const senha = document.getElementById("reg-senha")?.value || "";

        if (!telegram) {
            exibirAlerta("O @Telegram é obrigatório para criar sua conta (RN03).");
            return;
        }
        if (!telegram.startsWith("@")) {
            telegram = "@" + telegram;
        }

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    nome,
                    email,
                    telegram,
                    telegram_username: telegram,
                    telegram_id,
                    senha
                })
            });
            const data = await res.json();

            if (!res.ok || !data.sucesso) {
                exibirAlerta(data.erro || "Erro ao criar conta.");
                return;
            }

            exibirAlerta("Conta criada com sucesso! Faça login para receber seu código de 1º acesso (2FA).", "sucesso");
            formReg.reset();
        } catch (err) {
            exibirAlerta("Erro de comunicação ao tentar registrar usuário.");
        }
    });
}

// Adicione/atualize no seu web/js/auth.js:

document.addEventListener("DOMContentLoaded", () => {
    configurarFormularioEsqueciSenha();
    configurarFormularioRedefinirSenha();

    // Se o usuário clicou no link de recuperação recebido no e-mail (?reset_token=...)
    const params = new URLSearchParams(window.location.search);
    if (params.has("reset_token")) {
        window.tokenResetUrl = params.get("reset_token");
        const viewLogin = document.getElementById("view-login");
        const viewReset = document.getElementById("view-reset-password");
        if (viewLogin && viewReset) {
            viewLogin.classList.remove("active");
            viewLogin.style.display = "none";
            viewReset.classList.add("active");
            viewReset.style.display = "block";
        }
    }
});

function configurarFormularioEsqueciSenha() {
    const formEsqueci = document.getElementById("form-esqueci-senha");
    if (!formEsqueci || formEsqueci.dataset.bound) return;
    formEsqueci.dataset.bound = "1";

    formEsqueci.addEventListener("submit", async (e) => {
        e.preventDefault();
        const inputEmail = document.getElementById("recuperar-email");
        const forgotAlert = document.getElementById("forgot-alert");
        const btnEnviar = document.getElementById("btn-enviar-recuperacao");
        const email = (inputEmail?.value || "").trim();

        if (!email || !email.includes("@")) {
            if (forgotAlert) {
                forgotAlert.style.display = "block";
                forgotAlert.className = "alert-box alert-error";
                forgotAlert.textContent = "Digite um e-mail válido.";
            }
            return;
        }

        if (btnEnviar) {
            btnEnviar.disabled = true;
            btnEnviar.textContent = "Enviando...";
        }

        try {
            const res = await fetch("/api/auth/recuperar-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ email })
            });
            const data = await res.json();

            if (forgotAlert) {
                forgotAlert.style.display = "block";
                if (res.ok && data.sucesso) {
                    forgotAlert.className = "alert-box alert-success";
                    const extra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                    forgotAlert.textContent = (data.mensagem || "Link enviado para seu e-mail!") + extra;
                    formEsqueci.reset();
                } else {
                    forgotAlert.className = "alert-box alert-error";
                    forgotAlert.textContent = data.erro || "Não foi possível enviar o link.";
                }
            }
        } catch (err) {
            if (forgotAlert) {
                forgotAlert.style.display = "block";
                forgotAlert.className = "alert-box alert-error";
                forgotAlert.textContent = "Erro de conexão com o servidor.";
            }
        } finally {
            if (btnEnviar) {
                btnEnviar.disabled = false;
                btnEnviar.textContent = "Enviar Link";
            }
        }
    });
}

function configurarFormularioRedefinirSenha() {
    const formReset = document.getElementById("form-reset-password");
    if (!formReset || formReset.dataset.bound) return;
    formReset.dataset.bound = "1";

    formReset.addEventListener("submit", async (e) => {
        e.preventDefault();
        const novaSenha = document.getElementById("nova-senha-reset")?.value || "";
        const params = new URLSearchParams(window.location.search);
        const token = window.tokenResetUrl || params.get("reset_token") || "";

        if (novaSenha.length < 6) {
            alert("A nova senha deve ter pelo menos 6 caracteres.");
            return;
        }

        try {
            const res = await fetch("/api/auth/redefinir-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ token, nova_senha: novaSenha })
            });
            const data = await res.json();
            if (res.ok && data.sucesso) {
                alert("Senha alterada com sucesso! Faça login com sua nova senha.");
                window.location.href = "/";
            } else {
                alert(data.erro || "Link inválido ou expirado.");
            }
        } catch (err) {
            alert("Erro ao conectar ao servidor para salvar a nova senha.");
        }
    });
}