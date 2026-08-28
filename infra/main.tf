locals {
  # As 3 Lambdas que fazem I/O real no data lake (Bronze/Silver/Gold).
  data_lambdas = toset(["extract", "transform", "load"])

  # Timeout/memória por Lambda -- extract pode demorar dependendo do
  # RESULTS_LIMIT (scraping via Apify); orchestrator precisa cobrir a soma
  # das 3 etapas, até o teto de 15 min (900s) do Lambda.
  lambda_settings = {
    extract      = { timeout = 300, memory = 512 }
    transform    = { timeout = 120, memory = 1024 }
    load         = { timeout = 120, memory = 1024 }
    orchestrator = { timeout = 900, memory = 256 }
  }
}

# ── Data lake ────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
}

# ── Repositórios ECR (um por Lambda, incluindo a orquestradora) ──────────

resource "aws_ecr_repository" "lambdas" {
  for_each = toset(["extract", "transform", "load", "orchestrator"])

  name         = "${var.project_name}-${each.key}"
  force_delete = true
}

# ── IAM: papel de execução comum ──────────────────────────────────────────

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ── IAM: extract/transform/load leem e escrevem no bucket do data lake ───

resource "aws_iam_role" "data_lambda" {
  for_each = local.data_lambdas

  name               = "${var.project_name}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "data_lambda_basic_execution" {
  for_each = local.data_lambdas

  role       = aws_iam_role.data_lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "data_lake_access" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/*"]
  }
}

resource "aws_iam_role_policy" "data_lambda_s3_access" {
  for_each = local.data_lambdas

  name   = "${var.project_name}-${each.key}-s3-access"
  role   = aws_iam_role.data_lambda[each.key].id
  policy = data.aws_iam_policy_document.data_lake_access.json
}

# ── IAM: orquestradora só pode invocar as 3 Lambdas de dados ─────────────

resource "aws_iam_role" "orchestrator" {
  name               = "${var.project_name}-orchestrator-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "orchestrator_basic_execution" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "invoke_data_lambdas" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [for name in local.data_lambdas : aws_lambda_function.data_lambda[name].arn]
  }
}

resource "aws_iam_role_policy" "orchestrator_invoke_access" {
  name   = "${var.project_name}-orchestrator-invoke-access"
  role   = aws_iam_role.orchestrator.id
  policy = data.aws_iam_policy_document.invoke_data_lambdas.json
}

# ── Lambdas: extract, transform, load ─────────────────────────────────────

resource "aws_lambda_function" "data_lambda" {
  for_each = local.data_lambdas

  function_name = "${var.project_name}-${each.key}"
  role          = aws_iam_role.data_lambda[each.key].arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambdas[each.key].repository_url}:${var.image_tag}"
  timeout       = local.lambda_settings[each.key].timeout
  memory_size   = local.lambda_settings[each.key].memory

  environment {
    variables = merge(
      {
        S3_BUCKET        = aws_s3_bucket.data_lake.bucket
        S3_BRONZE_PREFIX = "bronze/"
        S3_SILVER_PREFIX = "silver/"
        S3_GOLD_PREFIX   = "gold/"
      },
      each.key == "extract" ? { APIFY_API_TOKEN = var.apify_api_token } : {}
    )
  }
}

# ── Lambda orquestradora ───────────────────────────────────────────────────

resource "aws_lambda_function" "orchestrator" {
  function_name = "${var.project_name}-orchestrator"
  role          = aws_iam_role.orchestrator.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambdas["orchestrator"].repository_url}:${var.image_tag}"
  timeout       = local.lambda_settings.orchestrator.timeout
  memory_size   = local.lambda_settings.orchestrator.memory

  environment {
    variables = {
      EXTRACT_FUNCTION_NAME   = aws_lambda_function.data_lambda["extract"].function_name
      TRANSFORM_FUNCTION_NAME = aws_lambda_function.data_lambda["transform"].function_name
      LOAD_FUNCTION_NAME      = aws_lambda_function.data_lambda["load"].function_name
    }
  }
}
