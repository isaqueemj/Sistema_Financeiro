# Caminho: core/email_service.py
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def enviar_email_sistema(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str) -> dict:
    """
    Envia e-mails transacionais (2FA e Recuperação de Senha) via SMTP.
    Caso as variáveis SMTP_EMAIL / SMTP_PASSWORD não estejam configuradas no .env,
    exibe o código/link diretamente no terminal para não travar os testes locais.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip())
    smtp_email = os.getenv("SMTP_EMAIL", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")

    # Log de segurança no terminal para facilitar testes em desenvolvimento
    print("\n" + "=" * 65)
    print(f"📧 [DISPARO DE E-MAIL] Para: {destinatario}")
    print(f"📌 Assunto: {assunto}")
    print(f"📄 Conteúdo:\n{corpo_texto}")
    print("=" * 65 + "\n")

    if not smtp_email or not smtp_password or "seu_email" in smtp_email:
        return {
            "enviado_smtp": False,
            "aviso": "SMTP não configurado no .env. Verifique o código/link impresso no terminal do VS Code."
        }

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = f"FinanceControl Segurança <{smtp_email}>"
    msg["To"] = destinatario
    msg.set_content(corpo_texto)
    msg.add_alternative(corpo_html, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        return {"enviado_smtp": True}
    except Exception as e:
        print(f"⚠️ [ERRO SMTP] Falha ao enviar e-mail para {destinatario}: {e}")
        return {
            "enviado_smtp": False,
            "erro_smtp": str(e),
            "aviso": "Falha na autenticação SMTP. O código/link foi exibido no terminal do servidor."
        }


def enviar_email_codigo_2fa(destinatario: str, nome: str, codigo: str) -> dict:
    assunto = f"🔐 Seu código de verificação 2FA: {codigo} - FinanceControl"
    corpo_texto = (
        f"Olá, {nome}!\n\n"
        f"Seu código de verificação de 2 fatores (2FA) para o FinanceControl é: {codigo}\n"
        f"Este código expira em 10 minutos.\n"
    )
    corpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #0b1320; color: #f8fafc; padding: 28px; border-radius: 14px; border: 1px solid #1e293b;">
        <h2 style="color: #3b82f6; margin-top: 0;">💎 FinanceControl</h2>
        <p style="color: #cbd5e1; font-size: 15px;">Olá, <strong>{nome}</strong>!</p>
        <p style="color: #94a3b8; font-size: 14px; line-height: 1.5;">
            Identificamos o seu acesso ao sistema. Utilize o código de 6 dígitos abaixo para concluir a verificação em duas etapas (2FA):
        </p>
        <div style="background: #152238; border: 1px solid #10b981; border-radius: 10px; padding: 18px; text-align: center; margin: 22px 0;">
            <span style="font-size: 28px; font-weight: bold; letter-spacing: 8px; color: #10b981;">{codigo}</span>
        </div>
        <p style="color: #64748b; font-size: 12px;">Este código é válido por 10 minutos.</p>
    </div>
    """
    return enviar_email_sistema(destinatario, assunto, corpo_html, corpo_texto)


def enviar_email_recuperacao_senha(destinatario: str, nome: str, link_redefinicao: str) -> dict:
    assunto = "🔑 Redefinição de Senha - FinanceControl"
    corpo_texto = (
        f"Olá, {nome}!\n\n"
        f"Recebemos uma solicitação para redefinir sua senha no FinanceControl.\n"
        f"Acesse o link abaixo para criar uma nova senha (válido por 15 minutos):\n"
        f"{link_redefinicao}\n"
    )
    corpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #0b1320; color: #f8fafc; padding: 28px; border-radius: 14px; border: 1px solid #1e293b;">
        <h2 style="color: #3b82f6; margin-top: 0;">💎 FinanceControl</h2>
        <p style="color: #cbd5e1; font-size: 15px;">Olá, <strong>{nome}</strong>!</p>
        <p style="color: #94a3b8; font-size: 14px; line-height: 1.5;">
            Você solicitou a recuperação de senha da sua conta. Clique no botão abaixo para cadastrar uma nova senha:
        </p>
        <div style="text-align: center; margin: 26px 0;">
            <a href="{link_redefinicao}" style="background: #3b82f6; color: #ffffff; text-decoration: none; padding: 13px 26px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
                REDEFINIR MINHA SENHA
            </a>
        </div>
        <p style="color: #94a3b8; font-size: 12px; word-break: break-all;">
            Ou copie e cole este link no navegador:<br>
            <a href="{link_redefinicao}" style="color: #60a5fa;">{link_redefinicao}</a>
        </p>
        <p style="color: #64748b; font-size: 12px;">Este link expira em 15 minutos.</p>
    </div>
    """
    return enviar_email_sistema(destinatario, assunto, corpo_html, corpo_texto)