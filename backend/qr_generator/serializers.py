from rest_framework import serializers


class QRPDFUploadSerializer(serializers.Serializer):
    file = serializers.FileField(
        required=True,
        help_text="CSV file containing title and caption columns.",
    )

    def validate_file(self, value):
        if not value.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Only CSV files are allowed.")

        return value
