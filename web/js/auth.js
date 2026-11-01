// Caminho: web/js/auth.js

let estadoAtual = "login";
let identificadorPendente2FA = "";
let tokenResetUrl = null;

document.addEventListener("DOMContentLoaded", () => {
    configurarBotoesOlhoSenha();
    configurarAlternanciaSplitScreen();
    configurarInputsOTP2FA();
    configurarFormularioLogin();
    configurarFormulario2FA();
    configurarFormularioCadastro();
    configurarFormularioEsqueciSenha();
    configurarFormularioRedefinirSenha();

    // Se abriu o link vindo do e-mail (?reset_token=...), exibe a tela de Nova Senha
    const params = new URLSearchParams(window.location.search);
    if (params.has("reset_token")) {
        tokenResetUrl = params.get("reset_token");
        mostrarVisao("reset-password");
    }
});

/* ==========================================================
   1. MOSTRAR / OCULTAR SENHA (ÍCONE DE OLHO)
========================================================== */
function configurarBotoesOlhoSenha() {
    document.querySelectorAll(".btn-toggle-password").forEach((botao) => {
        botao.addEventListener("click", () => {
            const targetId = botao.getAttribute("data-target");
            const inputSenha = document.getElementById(targetId);
            const icone = botao.querySelector("i");
            if (!inputSenha) return;

            if (inputSenha.type === "password") {
                inputSenha.type = "text";
                if (icone) icone.classList.replace("bi-eye", "bi-eye-slash");
            } else {
                inputSenha.type = "password";
                if (icone) icone.classList.replace("bi-eye-slash", "bi-eye");
            }
        });
    });
}

/* ==========================================================
   2. ALTERNÂNCIA DE TELAS (LOGIN / 2FA / CADASTRO / RESET)
========================================================== */
function configurarAlternanciaSplitScreen() {
    const btnAlternar = document.getElementById("btn-alternar-modo");
    const btnVoltarLogin = document.getElementById("btn-voltar-login");

    if (btnAlternar) {
        btnAlternar.addEventListener("click", () => {
            if (estadoAtual === "login" || estadoAtual === "2fa" || estadoAtual === "reset-password") {
                mostrarVisao("register");
            } else {
                mostrarVisao("login");
            }
        });
    }

    if (btnVoltarLogin) {
        btnVoltarLogin.addEventListener("click", () => mostrarVisao("login"));
    }
}

function mostrarVisao(novaVisao) {
    estadoAtual = novaVisao;
    ocultarAlerta("auth-alert");

    const views = {
        "login": document.getElementById("view-login"),
        "2fa": document.getElementById("view-2fa"),
        "register": document.getElementById("view-register"),
        "reset-password": document.getElementById("view-reset-password")
    };

    Object.values(views).forEach((v) => {
        if (v) {
            v.classList.remove("active");
            v.style.display = "none";
        }
    });

    const viewAtiva = views[novaVisao];
    if (viewAtiva) {
        viewAtiva.classList.add("active");
        viewAtiva.style.display = "block";
    }

    const ctaTitulo = document.getElementById("cta-titulo");
    const ctaDescricao = document.getElementById("cta-descricao");
    const btnAlternar = document.getElementById("btn-alternar-modo");

    if (ctaTitulo && ctaDescricao && btnAlternar) {
        if (novaVisao === "register") {
            ctaTitulo.textContent = "Já possui conta?";
            ctaDescricao.textContent = "Acesse agora usando seu e-mail ou seu @Telegram vinculado.";
            btnAlternar.textContent = "FAZER LOGIN";
        } else {
            ctaTitulo.textContent = "Novo por aqui?";
            ctaDescricao.textContent = "Cadastre-se vinculando seu @Telegram obrigatório e registre gastos por linguagem natural com gráficos em tempo real.";
            btnAlternar.textContent = "CRIAR CONTA";
        }
    }

    if (novaVisao === "2fa") {
        setTimeout(() => {
            const primeiroInput = document.querySelector(".otp-input");
            if (primeiroInput) primeiroInput.focus();
        }, 80);
    }
}

function validarIdentificadorHibrido(valor) {
    const limpo = (valor || "").trim();
    const regexEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const regexTelegram = /^@[a-zA-Z0-9_]{3,32}$/;

    if (regexEmail.test(limpo)) {
        return { valido: true, tipo: "email", valorNormalizado: limpo.toLowerCase() };
    }
    if (regexTelegram.test(limpo)) {
        return { valido: true, tipo: "telegram", valorNormalizado: limpo };
    }
    if (/^[a-zA-Z0-9_]{3,32}$/.test(limpo)) {
        return { valido: true, tipo: "telegram", valorNormalizado: "@" + limpo };
    }
    return { valido: false, tipo: null, valorNormalizado: limpo };
}

/* ==========================================================
   3. FORMULÁRIO DE LOGIN E ENTRADA NA ETAPA 2FA
========================================================== */
function configurarFormularioLogin() {
    const formLogin = document.getElementById("form-login");
    if (!formLogin) return;

    formLogin.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const inputIdent = document.getElementById("login-identificador");
        const inputSenha = document.getElementById("login-senha");
        const btnEntrar = document.getElementById("btn-entrar");

        const validacao = validarIdentificadorHibrido(inputIdent ? inputIdent.value : "");
        if (!validacao.valido) {
            exibirAlerta("auth-alert", "Informe um E-mail válido ou seu @usuário do Telegram.", "error");
            if (inputIdent) inputIdent.focus();
            return;
        }

        if (!inputSenha || !inputSenha.value) {
            exibirAlerta("auth-alert", "Por favor, insira sua senha.", "error");
            if (inputSenha) inputSenha.focus();
            return;
        }

        if (btnEntrar) {
            btnEntrar.disabled = true;
            btnEntrar.innerHTML = `<span>Autenticando...</span>`;
        }

        try {
            const response = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    identificador: validacao.valorNormalizado,
                    email: validacao.valorNormalizado,
                    senha: inputSenha.value
                })
            });

            const data = await response.json();

            if (response.ok && data.requer_2fa) {
                identificadorPendente2FA = data.identificador || validacao.valorNormalizado;
                const elEmailDestino = document.getElementById("twofa-email-destino");
                if (elEmailDestino) {
                    elEmailDestino.textContent = data.email_mascarado || validacao.valorNormalizado;
                }
                document.querySelectorAll(".otp-input").forEach((inp) => (inp.value = ""));
                mostrarVisao("2fa");

                const msgExtra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                exibirAlerta("auth-alert", `Código de 6 dígitos enviado para ${data.email_mascarado || validacao.valorNormalizado}!${msgExtra}`, "success");
                return;
            }

            if (response.ok && data.sucesso) {
                localStorage.setItem("usuario_logado", JSON.stringify(data.usuario || {}));
                window.location.replace("/pages/dashboard.html");
            } else {
                exibirAlerta("auth-alert", data.erro || "Credenciais inválidas.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro de conexão com o servidor Flask.", "error");
        } finally {
            if (btnEntrar) {
                btnEntrar.disabled = false;
                btnEntrar.innerHTML = `<span>ENTRAR</span><i class="bi bi-arrow-right-short fs-5"></i>`;
            }
        }
    });
}

/* ==========================================================
   4. AVANÇO AUTOMÁTICO E OPÇÃO DE COLAR NOS 6 DÍGITOS DO 2FA
========================================================== */
function preencherCodigoNosInputsOTP(textoBruto) {
    const inputs = Array.from(document.querySelectorAll(".otp-input"));
    const digitos = (textoBruto || "").replace(/\D/g, "").slice(0, inputs.length);
    if (!digitos) return;

    inputs.forEach((inp, idx) => {
        inp.value = digitos[idx] || "";
    });

    const proximoIndice = Math.min(digitos.length, inputs.length - 1);
    if (inputs[proximoIndice]) {
        inputs[proximoIndice].focus();
    }
}

function configurarInputsOTP2FA() {
    const inputs = Array.from(document.querySelectorAll(".otp-input"));

    inputs.forEach((input, index) => {
        // Caso o usuário digite ou cole mais de 1 caractere diretamente no input
        input.addEventListener("input", (e) => {
            const apenasNumeros = (e.target.value || "").replace(/\D/g, "");

            if (apenasNumeros.length > 1) {
                preencherCodigoNosInputsOTP(apenasNumeros);
                return;
            }

            e.target.value = apenasNumeros;

            // Assim que digitar 1 número, passa imediatamente para o próximo quadrado
            if (apenasNumeros.length === 1 && index < inputs.length - 1) {
                inputs[index + 1].focus();
                inputs[index + 1].select();
            }
        });

        input.addEventListener("keydown", (e) => {
            // Se apertar um número em um campo já preenchido, substitui e avança
            if (/^[0-9]$/.test(e.key) && input.value && index < inputs.length - 1) {
                e.preventDefault();
                input.value = e.key;
                inputs[index + 1].focus();
                inputs[index + 1].select();
                return;
            }

            if (e.key === "Backspace") {
                if (!input.value && index > 0) {
                    e.preventDefault();
                    inputs[index - 1].value = "";
                    inputs[index - 1].focus();
                }
            } else if (e.key === "ArrowLeft" && index > 0) {
                e.preventDefault();
                inputs[index - 1].focus();
            } else if (e.key === "ArrowRight" && index < inputs.length - 1) {
                e.preventDefault();
                inputs[index + 1].focus();
            }
        });

        // Suporte a Ctrl+V / Colar em qualquer um dos 6 campos
        input.addEventListener("paste", (e) => {
            e.preventDefault();
            const textoColado = (e.clipboardData || window.clipboardData).getData("text");
            preencherCodigoNosInputsOTP(textoColado);
        });

        input.addEventListener("focus", () => input.select());
    });

    // Botão dedicado "Colar código da área de transferência"
    const btnColar = document.getElementById("btn-colar-2fa");
    if (btnColar) {
        btnColar.addEventListener("click", async () => {
            try {
                const texto = await navigator.clipboard.readText();
                const limpo = (texto || "").replace(/\D/g, "");
                if (!limpo) {
                    exibirAlerta("auth-alert", "Nenhum código numérico encontrado na área de transferência.", "error");
                    return;
                }
                preencherCodigoNosInputsOTP(limpo);
            } catch (_) {
                exibirAlerta("auth-alert", "Clique no 1º quadrado e pressione Ctrl + V para colar o código.", "error");
                if (inputs[0]) inputs[0].focus();
            }
        });
    }

    // Botão Reenviar Código 2FA
    const btnReenviar = document.getElementById("btn-reenviar-2fa");
    if (btnReenviar) {
        btnReenviar.addEventListener("click", async () => {
            if (!identificadorPendente2FA) return;
            btnReenviar.disabled = true;

            try {
                const res = await fetch("/api/auth/reenviar-2fa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "same-origin",
                    body: JSON.stringify({ identificador: identificadorPendente2FA })
                });
                const data = await res.json();
                if (res.ok && data.sucesso) {
                    const msgExtra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                    exibirAlerta("auth-alert", `Novo código de 6 dígitos enviado!${msgExtra}`, "success");
                } else {
                    exibirAlerta("auth-alert", data.erro || "Não foi possível reenviar o código.", "error");
                }
            } catch (_) {
                exibirAlerta("auth-alert", "Falha ao solicitar novo código 2FA.", "error");
            }

            let seg = 30;
            const timer = setInterval(() => {
                seg--;
                btnReenviar.textContent = `Reenviar em ${seg}s`;
                if (seg <= 0) {
                    clearInterval(timer);
                    btnReenviar.disabled = false;
                    btnReenviar.textContent = "Reenviar código por e-mail";
                }
            }, 1000);
        });
    }
}

/* ==========================================================
   5. VALIDAÇÃO DO 2FA E REDIRECIONAMENTO SEGURO PARA O DASHBOARD
========================================================== */
function configurarFormulario2FA() {
    const form2FA = document.getElementById("form-2fa");
    if (!form2FA) return;

    form2FA.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const codigo = Array.from(document.querySelectorAll(".otp-input"))
            .map((i) => (i.value || "").trim())
            .join("");

        if (codigo.length < 6) {
            exibirAlerta("auth-alert", "Digite todos os 6 dígitos do código enviado ao seu e-mail.", "error");
            return;
        }

        const btnValidar = document.getElementById("btn-validar-2fa");
        if (btnValidar) {
            btnValidar.disabled = true;
            btnValidar.innerHTML = `<span>Validando acesso...</span>`;
        }

        try {
            const res = await fetch("/api/auth/verificar-2fa", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    identificador: identificadorPendente2FA,
                    codigo: codigo
                })
            });

            const data = await res.json();
            if (res.ok && data.sucesso) {
                localStorage.setItem("usuario_logado", JSON.stringify(data.usuario || {}));
                exibirAlerta("auth-alert", "2FA confirmado com sucesso! Abrindo seu Dashboard...", "success");
                window.location.replace(data.redirect || "/pages/dashboard.html");
                return;
            } else {
                exibirAlerta("auth-alert", data.erro || "Código 2FA incorreto ou expirado.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro ao validar o código 2FA no servidor.", "error");
        } finally {
            if (btnValidar) {
                btnValidar.disabled = false;
                btnValidar.innerHTML = `<i class="bi bi-check2-circle"></i><span>VERIFICAR E ACESSAR</span>`;
            }
        }
    });
}

/* ==========================================================
   6. CADASTRO COM @TELEGRAM OBRIGATÓRIO
========================================================== */
function configurarFormularioCadastro() {
    const formRegister = document.getElementById("form-register");
    if (!formRegister) return;

    formRegister.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const nome = (document.getElementById("reg-nome")?.value || "").trim();
        const email = (document.getElementById("reg-email")?.value || "").trim();
        let telegram = (document.getElementById("reg-telegram")?.value || "").trim();
        const senha = document.getElementById("reg-senha")?.value || "";

        if (!nome || !email) {
            exibirAlerta("auth-alert", "Nome e E-mail são obrigatórios.", "error");
            return;
        }

        if (!telegram) {
            exibirAlerta("auth-alert", "O campo @Telegram é obrigatório para usar o sistema (RN03).", "error");
            document.getElementById("reg-telegram")?.focus();
            return;
        }

        if (!telegram.startsWith("@")) {
            telegram = "@" + telegram;
        }

        if (!/^@[a-zA-Z0-9_]{3,32}$/.test(telegram)) {
            exibirAlerta("auth-alert", "Informe um @Telegram válido (ex: @seu_usuario).", "error");
            document.getElementById("reg-telegram")?.focus();
            return;
        }

        if (senha.length < 6) {
            exibirAlerta("auth-alert", "A senha deve ter no mínimo 6 caracteres.", "error");
            return;
        }

        const btnCadastrar = document.getElementById("btn-cadastrar");
        if (btnCadastrar) {
            btnCadastrar.disabled = true;
            btnCadastrar.innerHTML = `<span>Cadastrando...</span>`;
        }

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    nome,
                    email,
                    telegram,
                    telegram_username: telegram,
                    senha
                })
            });

            const data = await res.json();
            if (res.ok && data.sucesso) {
                mostrarVisao("login");
                const inputIdent = document.getElementById("login-identificador");
                if (inputIdent) inputIdent.value = email;
                exibirAlerta(
                    "auth-alert",
                    "Conta criada com sucesso! Faça seu 1º login para receber o código 2FA no seu e-mail.",
                    "success"
                );
                formRegister.reset();
            } else {
                exibirAlerta("auth-alert", data.erro || "Erro ao realizar cadastro.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro de conexão com o servidor.", "error");
        } finally {
            if (btnCadastrar) {
                btnCadastrar.disabled = false;
                btnCadastrar.innerHTML = `<span>CADASTRAR COM SEGURANÇA</span>`;
            }
        }
    });
}

/* ==========================================================
   7. RECUPERAÇÃO E ALTERAÇÃO DE SENHA (COM CONFIRMAÇÃO DE SENHA)
========================================================== */
function configurarFormularioEsqueciSenha() {
    const formEsqueci = document.getElementById("form-esqueci-senha");
    if (!formEsqueci) return;

    formEsqueci.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("forgot-alert");

        const inputEmail = document.getElementById("recuperar-email");
        const email = (inputEmail?.value || "").trim();

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            exibirAlerta("forgot-alert", "Digite um e-mail válido.", "error");
            return;
        }

        const btnEnviar = document.getElementById("btn-enviar-recuperacao");
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

            if (res.ok && data.sucesso) {
                const msgExtra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                exibirAlerta("forgot-alert", `${data.mensagem || "Link enviado!"}${msgExtra}`, "success");
                formEsqueci.reset();
            } else {
                exibirAlerta("forgot-alert", data.erro || "Não foi possível enviar o e-mail de recuperação.", "error");
            }
        } catch (err) {
            exibirAlerta("forgot-alert", "Erro de comunicação com o servidor.", "error");
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
    if (!formReset) return;

    formReset.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const novaSenha = document.getElementById("nova-senha-reset")?.value || "";
        const confirmarSenha = document.getElementById("confirmar-senha-reset")?.value || "";
        const params = new URLSearchParams(window.location.search);
        const token = tokenResetUrl || params.get("reset_token") || "";

        if (!novaSenha || novaSenha.length < 6) {
            exibirAlerta("auth-alert", "A nova senha deve ter no mínimo 6 caracteres.", "error");
            document.getElementById("nova-senha-reset")?.focus();
            return;
        }

        if (novaSenha !== confirmarSenha) {
            exibirAlerta("auth-alert", "As senhas não coincidem. Digite a mesma senha nos dois campos.", "error");
            document.getElementById("confirmar-senha-reset")?.focus();
            return;
        }

        const btnSalvar = document.getElementById("btn-salvar-nova-senha");
        if (btnSalvar) {
            btnSalvar.disabled = true;
            btnSalvar.innerHTML = `<span>Salvando...</span>`;
        }

        try {
            const res = await fetch("/api/auth/redefinir-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    token: token,
                    nova_senha: novaSenha,
                    confirmar_senha: confirmarSenha
                })
            });
            const data = await res.json();

            if (res.ok && data.sucesso) {
                window.history.replaceState({}, document.title, "/");
                formReset.reset();
                mostrarVisao("login");
                exibirAlerta("auth-alert", "Senha alterada com sucesso! Faça login com sua nova senha.", "success");
            } else {
                exibirAlerta("auth-alert", data.erro || "Link inválido ou expirado.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro ao conectar ao servidor.", "error");
        } finally {
            if (btnSalvar) {
                btnSalvar.disabled = false;
                btnSalvar.innerHTML = `<span>SALVAR NOVA SENHA</span>`;
            }
        }
    });
}

function exibirAlerta(elementId, mensagem, tipo) {
    const box = document.getElementById(elementId);
    if (!box) return;
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
}

function ocultarAlerta(elementId) {
    const box = document.getElementById(elementId);
    if (box) box.style.display = "none";
}