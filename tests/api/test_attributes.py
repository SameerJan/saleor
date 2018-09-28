import json

import pytest

import graphene
from django.shortcuts import reverse
from django.template.defaultfilters import slugify
from saleor.graphql.product.types import (
    AttributeValueType, resolve_attribute_value_type)
from saleor.graphql.product.utils import attributes_to_hstore
from saleor.product.models import Attribute, AttributeValue, Category
from tests.utils import get_graphql_content


def test_attributes_to_hstore(product, color_attribute):
    color_value = color_attribute.values.first()

    # test transforming slugs of existing attributes to IDs
    input_data = [{
        'slug': color_attribute.slug, 'value': color_value.slug}]
    attrs_qs = product.product_type.product_attributes.all()
    ids = attributes_to_hstore(input_data, attrs_qs)
    assert str(color_attribute.pk) in ids
    assert ids[str(color_attribute.pk)] == str(color_value.pk)

    # test creating a new attribute value
    input_data = [{
        'slug': color_attribute.slug, 'value': 'Space Grey'}]
    ids = attributes_to_hstore(input_data, attrs_qs)
    new_value = AttributeValue.objects.get(slug='space-grey')
    assert str(color_attribute.pk) in ids
    assert ids[str(color_attribute.pk)] == str(new_value.pk)

    # test passing an attribute that doesn't belong to this product raises
    # an error
    input_data = [{'slug': 'not-an-attribute', 'value': 'not-a-value'}]
    with pytest.raises(ValueError):
        attributes_to_hstore(input_data, attrs_qs)


def test_attributes_query(user_api_client, product):
    attributes = Attribute.objects.prefetch_related('values')
    query = '''
    query {
        attributes {
            edges {
                node {
                    id
                    name
                    slug
                    values {
                        id
                        name
                        slug
                    }
                }
            }
        }
    }
    '''
    response = user_api_client.post(reverse('api'), {'query': query})
    content = get_graphql_content(response)
    assert 'errors' not in content
    attributes_data = content['data']['attributes']['edges']
    assert len(attributes_data) == attributes.count()


def test_attributes_in_category_query(user_api_client, product):
    category = Category.objects.first()
    query = '''
    query {
        attributes(inCategory: "%(category_id)s") {
            edges {
                node {
                    id
                    name
                    slug
                    values {
                        id
                        name
                        slug
                    }
                }
            }
        }
    }
    ''' % {'category_id': graphene.Node.to_global_id('Category', category.id)}
    response = user_api_client.post(reverse('api'), {'query': query})
    content = get_graphql_content(response)
    assert 'errors' not in content
    attributes_data = content['data']['attributes']['edges']
    assert len(attributes_data) == Attribute.objects.count()


CREATE_ATTRIBUTES_QUERY = """
    mutation createAttribute(
            $name: String!, $values: [AttributeCreateValueInput]) {
        attributeCreate(
                input: {name: $name, values: $values}) {
            errors {
                field
                message
            }
            attribute {
                name
                slug
                values {
                    name
                    slug
                }
            }
        }
    }
"""


def test_create_attribute(admin_api_client):
    query = CREATE_ATTRIBUTES_QUERY
    name = 'Test name'
    variables = json.dumps({'name': name, 'values': []})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    assert not content['data']['attributeCreate']['errors']
    data = content['data']['attributeCreate']['attribute']
    assert data['name'] == name
    assert data['slug'] == slugify(name)
    assert not data['values']


def test_create_attribute_and_attribute_values(admin_api_client):
    query = CREATE_ATTRIBUTES_QUERY
    name = 'Value name'
    variables = json.dumps({
        'name': 'Example name', 'values': [{'name': name, 'value': '#1231'}]})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    assert not content['data']['attributeCreate']['errors']
    data = content['data']['attributeCreate']['attribute']['values']
    assert len(data) == 1
    assert data[0]['name'] == name
    assert data[0]['slug'] == slugify(name)


def test_create_attribute_and_attribute_values_errors(admin_api_client):
    query = CREATE_ATTRIBUTES_QUERY
    variables = json.dumps({
        'name': 'Example name', 'slug': 'example-slug',
        'values': [
            {'name': 'Red Color', 'value': '#1231'},
            {'name': 'Red Color', 'value': '#121'}]})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    errors = content['data']['attributeCreate']['errors']
    assert errors
    assert errors[0]['field'] == 'values'
    assert errors[0]['message'] == 'Duplicated attribute value names provided.'


def test_update_attribute(admin_api_client, color_attribute):
    attribute = color_attribute
    query = """
    mutation updateAttribute($id: ID!, $name: String!, $slug: String!) {
        attributeUpdate(id: $id, input: {name: $name, slug: $slug}) {
            attribute {
                name
            }
        }
    }
    """
    name = 'Wings name'
    slug = attribute.slug
    id = graphene.Node.to_global_id('Attribute', attribute.id)
    variables = json.dumps({'name': name, 'id': id, 'slug': slug})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    attribute.refresh_from_db()
    assert 'errors' not in content
    data = content['data']['attributeUpdate']['attribute']
    assert data['name'] == name == attribute.name


def test_delete_attribute(admin_api_client, color_attribute):
    attribute = color_attribute
    query = """
    mutation deleteAttribute($id: ID!) {
        attributeDelete(id: $id) {
            attribute {
                id
            }
        }
    }
    """
    id = graphene.Node.to_global_id('Attribute', attribute.id)
    variables = json.dumps({'id': id})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    with pytest.raises(attribute._meta.model.DoesNotExist):
        attribute.refresh_from_db()


def test_create_attribute_value(admin_api_client, color_attribute):
    attribute = color_attribute
    query = """
    mutation createChoice($attribute: ID!, $name: String!, $value: String!) {
        attributeValueCreate(
        input: {attribute: $attribute, name: $name, value: $value}) {
            attributeValue {
                name
                slug
                type
                value
            }
        }
    }
    """
    attribute_id = graphene.Node.to_global_id('Attribute', attribute.id)
    name = 'test name'
    value = 'test-string'
    variables = json.dumps(
        {'name': name, 'value': value, 'attribute': attribute_id})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    data = content[
        'data']['attributeValueCreate']['attributeValue']
    assert data['name'] == name
    assert data['slug'] == slugify(name)
    assert data['value'] == value
    assert data['type'] == 'STRING'


def test_update_attribute_value(admin_api_client, pink_attribute_value):
    value = pink_attribute_value
    query = """
    mutation updateChoice(
            $id: ID!, $name: String!, $slug: String!, $value: String!) {
        attributeValueUpdate(
        id: $id, input: {name: $name, slug: $slug, value: $value}) {
            attributeValue {
                name
                slug
                value
            }
        }
    }
    """
    id = graphene.Node.to_global_id('AttributeValue', value.id)
    name = 'Crimson name'
    variables = json.dumps(
        {'name': name, 'value': '#RED', 'slug': 'slug', 'id': id})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    value.refresh_from_db()
    data = content[
        'data']['attributeValueUpdate']['attributeValue']
    assert data['name'] == name == value.name
    assert data['slug'] == slugify(name)


def test_delete_attribute_value(
        admin_api_client, color_attribute, pink_attribute_value):
    value = pink_attribute_value
    value = color_attribute.values.get(name='Red')
    query = """
    mutation updateChoice($id: ID!) {
        attributeValueDelete(id: $id) {
            attributeValue {
                name
                slug
            }
        }
    }
    """
    id = graphene.Node.to_global_id('AttributeValue', value.id)
    variables = json.dumps({'id': id})
    response = admin_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    with pytest.raises(value._meta.model.DoesNotExist):
        value.refresh_from_db()


@pytest.mark.parametrize('raw_value, expected_type', [
    ('#0000', AttributeValueType.COLOR),
    ('#FF69B4', AttributeValueType.COLOR),
    ('rgb(255, 0, 0)', AttributeValueType.COLOR),
    ('hsl(0, 100%, 50%)', AttributeValueType.COLOR),
    ('hsla(120,  60%, 70%, 0.3)', AttributeValueType.COLOR),
    ('rgba(100%, 255, 0, 0)', AttributeValueType.COLOR),
    ('http://example.com', AttributeValueType.URL),
    ('https://example.com', AttributeValueType.URL),
    ('ftp://example.com', AttributeValueType.URL),
    ('example.com', AttributeValueType.STRING),
    ('Foo', AttributeValueType.STRING),
    ('linear-gradient(red, yellow)', AttributeValueType.GRADIENT),
    ('radial-gradient(#0000, yellow)', AttributeValueType.GRADIENT),
])
def test_resolve_attribute_value_type(raw_value, expected_type):
    assert resolve_attribute_value_type(raw_value) == expected_type


def test_query_attribute_values(
        color_attribute, pink_attribute_value, user_api_client):
    attribute_id = graphene.Node.to_global_id(
        'Attribute', color_attribute.id)
    query = """
    query getAttribute($id: ID!) {
        attributes(id: $id) {
            edges {
                node {
                    id
                    name
                    values {
                        name
                        type
                        value
                    }
                }
            }
        }
    }
    """
    variables = json.dumps({'id': attribute_id})
    response = user_api_client.post(
        reverse('api'), {'query': query, 'variables': variables})
    content = get_graphql_content(response)
    assert 'errors' not in content
    data = content['data']['attributes']['edges'][0]['node']
    values = data['values']
    pink = [v for v in values if v['name'] == pink_attribute_value.name]
    assert len(pink) == 1
    pink = pink[0]
    assert pink['value'] == '#FF69B4'
    assert pink['type'] == 'COLOR'
