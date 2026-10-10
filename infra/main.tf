locals {
  # Unica Lambda do projeto (ADR 0039, decisao 8): baixa uma tag do Hugging
  # Face e reconstroi Bronze, Silver e Gold no S3. Sem agendamento e sem
  # extracao (Apify) na nuvem; modelagem pesada continua local.
  # O Snapshot e baixado em /tmp, entao o armazenamento efemero e ampliado.
  # Timeout no teto do Lambda (900s).
  rebuild_settings = {
    timeout   = 900
    memory    = 3008
    ephemeral = 5120 # MB em /tmp
  }
}

# ── Data lake ────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
}

# ── Repositorio ECR da Lambda de reconstrucao ────────────────────────────

resource "aws_ecr_repository" "lambdas" {
  for_each = toset(["rebuild"])

  name         = "${var.project_name}-${each.key}"
  force_delete = true
}

# ── IAM: papel de execucao minimo da Lambda rebuild ──────────────────────

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rebuild" {
  name               = "${var.project_name}-rebuild-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "rebuild_basic_execution" {
  role       = aws_iam_role.rebuild.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Leitura e escrita so no bucket do data lake (Bronze/Silver/Gold).
data "aws_iam_policy_document" "data_lake_access" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/*"]
  }
}

resource "aws_iam_role_policy" "rebuild_s3_access" {
  name   = "${var.project_name}-rebuild-s3-access"
  role   = aws_iam_role.rebuild.id
  policy = data.aws_iam_policy_document.data_lake_access.json
}

# ── Lambda rebuild ────────────────────────────────────────────────────────
# Evento: {"tag": "coleta_...", "run_id": "opcional"}. Invocacao manual
# (aws lambda invoke); nao ha gatilho agendado.

resource "aws_lambda_function" "rebuild" {
  function_name = "${var.project_name}-rebuild"
  role          = aws_iam_role.rebuild.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambdas["rebuild"].repository_url}:${var.image_tag}"
  timeout       = local.rebuild_settings.timeout
  memory_size   = local.rebuild_settings.memory

  ephemeral_storage {
    size = local.rebuild_settings.ephemeral
  }

  environment {
    variables = {
      S3_BUCKET       = aws_s3_bucket.data_lake.bucket
      HF_TOKEN        = var.hf_token
      HF_DATASET_REPO = var.hf_dataset_repo
    }
  }
}

# ── IAM/OIDC: GitHub Actions publica imagens no ECR sem credenciais estáticas ─
# Ver ADR 0009. terraform apply continua manual -- isto só permite que a
# esteira de CI publique imagens novas no ECR, nunca atualiza uma Lambda.

locals {
  github_repo = "Vini0606/Tecnicas-de-Ciencia-de-Dados-em-dados-do-Instagram"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # Thumbprint público e amplamente documentado do certificado raiz usado por
  # token.actions.githubusercontent.com. A AWS na prática ignora este valor
  # para emissores cuja CA já está na lista de confiança da AWS (caso do
  # GitHub Actions) -- o campo é obrigatório só pela forma (precisa de 40
  # caracteres hex), não é usado para validar de fato. Ver
  # https://docs.github.com/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1

  url = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_provider_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Só main -- nunca PRs/forks/outros branches. Rever se algum dia precisar
    # publicar a partir de outro branch (ex.: staging).
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions_oidc" {
  name               = "${var.project_name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

data "aws_iam_policy_document" "github_actions_ecr_push" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # exigido pela API do ECR -- não é escopável por recurso
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:BatchGetImage",
    ]
    resources = [for repo in aws_ecr_repository.lambdas : repo.arn]
  }
}

resource "aws_iam_role_policy" "github_actions_ecr_push" {
  name   = "${var.project_name}-github-actions-ecr-push"
  role   = aws_iam_role.github_actions_oidc.id
  policy = data.aws_iam_policy_document.github_actions_ecr_push.json
}

# ── ECR: mantém só as 10 imagens mais recentes por repositório ───────────
# Necessário porque, sem tag "latest" sobrescrita, cada merge relevante em
# main gera 1 imagem nova e imutáveis (ADR 0009).

resource "aws_ecr_lifecycle_policy" "lambdas" {
  for_each = aws_ecr_repository.lambdas

  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Manter só as 10 imagens mais recentes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
